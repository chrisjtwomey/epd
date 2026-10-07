// The install page: writes a board's firmware and network settings over USB.
//
// Every address here is relative, to the server's root by config.root, so
// the page works behind a reverse proxy at any path and inside a project's
// own layout. The only absolute ones are the links to this server's own
// HTTPS port, which a page opened over plain HTTP needs.
import { ESPLoader, Transport } from "./esptool-js-0.7.0.js";

const config = JSON.parse(document.getElementById("install-config").textContent);
const main = document.getElementById("install");

// The config keys a person sets, by the names the Settings page gives them.
const FIELDS = {
  "client.server_url": "Server address",
  "client.wifi.ssid": "Wi-Fi name",
  "client.wifi.password": "Wi-Fi password",
  "client.mqtt_host": "MQTT broker",
};

const BAUD_RATE = 460800;
const RESET_HOLD_MS = 200;

const firefox = navigator.userAgent.includes("Firefox/");

function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  node.append(...children);
  return node;
}

const message = (...parts) => el("p", {}, ...parts);
const note = (...parts) => el("p", { class: "note" }, ...parts);
const link = (address) => el("a", { href: address }, address);
const settings = () => (config.settingsUrl ? el("a", { href: config.settingsUrl }, "Settings") : "Settings");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function isIpAddress(host) {
  return /^\d{1,3}(\.\d{1,3}){3}$/.test(host) || host.startsWith("[");
}

function secureAddress(host, port) {
  return `https://${host}${port ? `:${port}` : ""}${location.pathname}`;
}

function start() {
  if (!window.isSecureContext) {
    if (!config.httpsPort) {
      main.append(message("Secure connection needed. Open this page through your reverse proxy, " +
                          "or turn on the HTTPS port in ", settings(), "."));
      return;
    }
    const byName = firefox && isIpAddress(location.hostname) && config.serverName;
    const address = secureAddress(byName ? config.serverName : location.hostname, config.httpsPort);
    main.append(message("Secure connection needed. Open ", link(address), "."),
                note("Your browser shows a warning first. Select Advanced, then continue."));
    return;
  }
  if (!("serial" in navigator)) {
    main.append(message("Your browser cannot install firmware. Try another browser."));
    return;
  }
  if (firefox && isIpAddress(location.hostname)) {
    main.append(config.serverName
      ? message("Your browser cannot install from an IP address. Open ",
                link(secureAddress(config.serverName, location.port)), ".")
      : message("Your browser cannot install from an IP address. Try another browser."));
    return;
  }
  if (config.missing.length) {
    const names = config.missing.map((key) => FIELDS[key] ?? key).join(", ");
    main.append(message(`Missing: ${names}. Add them in `, settings(), "."));
    return;
  }

  main.append(message("Connect a board with a USB cable, then select Install."));
  if (firefox) {
    main.append(note("Your browser first asks to install an add-on for this site. " +
                     "Select Continue to Installation, then Add."));
  }
  main.append(el("ul", { class: "boards" }, ...config.boards.map(boardRow)),
              note("Board not in the list? Use another USB cable: some carry only power."));
}

function boardRow(board) {
  const status = new Status();
  const heading = el("div", { class: "board" }, el("strong", {}, board.name));
  if (!board.version) {
    status.say("No firmware to install yet. It appears once the server has built it.");
  } else {
    const button = el("button", { type: "button" }, "Install");
    button.addEventListener("click", () => install(board, status));
    heading.append(el("span", { class: "version" }, board.version), button);
  }
  return el("li", {}, heading, status.node);
}

// What one board's row says while it installs.
class Status {
  constructor() {
    this.node = el("div", { class: "status", "aria-live": "polite" });
  }

  say(...parts) {
    this.node.replaceChildren(message(...parts));
  }

  fail(text) {
    this.node.replaceChildren(el("p", { class: "fault" }, text));
  }

  progress(fraction) {
    const percent = Math.floor(fraction * 100);
    this.node.replaceChildren(message(`Installing… ${percent}%`),
                              el("progress", { max: "100", value: String(percent) }),
                              note("Keep the board connected."));
  }
}

async function install(board, status) {
  const buttons = document.querySelectorAll("button");
  for (const button of buttons) button.disabled = true;
  try {
    await installOn(board, status);
  } finally {
    for (const button of buttons) button.disabled = false;
  }
}

async function installOn(board, status) {
  let port;
  try {
    port = await navigator.serial.requestPort({
      filters: board.usbVendorIds.map((usbVendorId) => ({ usbVendorId })),
    });
  } catch {
    status.fail("No board chosen. Select Install to try again.");
    return;
  }

  status.say("Connecting…");
  const product = encodeURIComponent(board.product);
  let files;
  try {
    files = await Promise.all([download(`${config.root}firmware.merged.bin?product=${product}`),
                               download(`${config.root}network.bin?product=${product}`)]);
  } catch (error) {
    status.fail(error.message);
    return;
  }

  const transport = new Transport(port, false);
  const loader = new ESPLoader({ transport, baudrate: BAUD_RATE, terminal: consoleTerminal });
  try {
    await loader.main();
  } catch (error) {
    await disconnect(transport);
    status.fail(portInUse(error)
      ? "Board in use by another app. Close that app, then select Install again."
      : "Board not responding. Hold BOOT while you press RST, then select Install again.");
    return;
  }
  if (loader.chip.CHIP_NAME !== board.chip) {
    await disconnect(transport);
    status.fail(`Wrong board: this one is not the ${board.name}. ` +
                "Select Install beside the board you connected.");
    return;
  }

  // The merged image fills the settings store's place with blank bytes, so
  // the network settings are written after it.
  const total = files[0].length + files[1].length;
  const before = [0, files[0].length];
  status.progress(0);
  try {
    await loader.writeFlash({
      fileArray: [{ data: files[0], address: 0 }, { data: files[1], address: config.storeOffset }],
      flashMode: "keep",
      flashFreq: "keep",
      flashSize: "keep",
      eraseAll: false,
      compress: true,
      reportProgress: (index, written, size) =>
        status.progress((before[index] + files[index].length * (written / size)) / total),
    });
  } catch {
    await disconnect(transport);
    status.fail("Install failed. Reconnect the board, then select Install again.");
    return;
  }

  status.say("Restarting the board…");
  await restart(transport);
  status.say("Installed. You can unplug the board.");
}

// A file from this server. A board's network settings that are no longer
// complete reload the page, which then names what is missing.
async function download(address) {
  const response = await fetch(address, { cache: "no-store" });
  if (response.status === 409) {
    location.reload();
    return new Promise(() => {});
  }
  if (!response.ok) {
    throw new Error((await response.text()).trim());
  }
  return new Uint8Array(await response.arrayBuffer());
}

// esptool's own restart: esptool-js 0.7.0's hard reset only lowers RTS, which
// leaves the board waiting.
async function restart(transport) {
  await transport.setDTR(false);
  await transport.setRTS(true);
  await sleep(RESET_HOLD_MS);
  await transport.setRTS(false);
  await sleep(RESET_HOLD_MS);
  await disconnect(transport);
}

async function disconnect(transport) {
  try {
    await transport.disconnect();
  } catch {
    // The port is gone already: a board that restarts drops its USB port.
  }
}

function portInUse(error) {
  return error?.name === "NetworkError" || /failed to open/i.test(String(error?.message));
}

const consoleTerminal = {
  clean() {},
  writeLine: (text) => console.debug(text),
  write: (text) => console.debug(text),
};

start();
