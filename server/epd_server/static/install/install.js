// The install page: writes a board's firmware and network settings over USB.
//
// Every address here is relative, to the server's root by config.root, so
// the page works behind a reverse proxy at any path and inside a project's
// own layout. The only absolute ones are the links to this server's own
// HTTPS port, which a page opened over plain HTTP needs.
import { ESPLoader, Transport } from "./esptool-js-0.7.0.js";

// A project's page can change these values while it is open, as when a
// person saves the network settings above the boards, so each install reads
// them again.
const readConfig = () => JSON.parse(document.getElementById("install-config").textContent);
let config = readConfig();
const main = document.getElementById("install");

// The config keys a person sets, by the names the Settings page gives them.
const FIELDS = {
  "client.server_url": "Server address",
  "client.wifi.ssid": "Wi-Fi name",
  "client.wifi.password": "Wi-Fi password",
  "client.mqtt_host": "MQTT broker",
};

// What a board logs once it is up, in epd's own words (firmware/src).
const LINES = {
  wifi: "wifi connected in",
  server: "reached the server at",
  mqtt: "connected to MQTT broker",
};

const BAUD_RATE = 460800;
const LOG_BAUD_RATE = 115200;
const RESET_HOLD_MS = 200;
// A board logs at once when it starts. Joining Wi-Fi may take a retry 30 s
// after a first try; the server and the broker answer soon after that.
const QUIET_LIMIT_MS = 10000;
const WIFI_LIMIT_MS = 60000;
const AFTER_WIFI_LIMIT_MS = { server: 60000, mqtt: 30000 };

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
// Where a person sets the network settings: on this page, on the project's
// install page, or in Settings.
const NETWORK_PLACE = config.networkHere ? "above"
  : config.networkUrl ? "on the install page" : "in Settings";
const networkLink = () => (config.networkHere ? ["above"]
  : config.networkUrl ? ["on ", el("a", { href: config.networkUrl }, "the install page")]
  : ["in ", settings()]);
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
    main.append(message(`Missing: ${names}. Add them `, ...networkLink(), "."));
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

  checklist(steps, passed) {
    this.node.replaceChildren(el("ul", { class: "steps" },
      ...steps.map((step) => el("li", passed.has(step.key) ? { class: "passed" } : {},
                                passed.has(step.key) ? step.passed : step.waiting))));
  }

  progress(fraction) {
    const percent = Math.floor(fraction * 100);
    this.node.replaceChildren(message(`Installing… ${percent}%`),
                              el("progress", { max: "100", value: String(percent) }),
                              note("Keep the board connected."));
  }
}

async function install(board, status) {
  config = readConfig();
  const buttons = main.querySelectorAll("button");
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
  await check(board, status);
}

// Follows the board's log after its restart, and says how its start went.
async function check(board, status) {
  const steps = [
    { key: "wifi", waiting: "Joining Wi-Fi…", passed: "Joined Wi-Fi" },
    { key: "server", waiting: "Reaching the server…", passed: "Reached the server" },
  ];
  if (config.mqttHost) {
    steps.push({ key: "mqtt", waiting: "Connecting to MQTT…", passed: "Connected to MQTT" });
  }
  const passed = new Set();
  const times = { start: Date.now(), heard: null, wifi: null };
  const deadline = () => {
    if (times.heard === null) return times.start + QUIET_LIMIT_MS;
    if (times.wifi === null) return times.heard + WIFI_LIMIT_MS;
    return Math.max(...steps.filter((step) => !passed.has(step.key))
                            .map((step) => times.wifi + AFTER_WIFI_LIMIT_MS[step.key]));
  };
  const onLine = (line) => {
    for (const step of steps) {
      if (!passed.has(step.key) && line.includes(LINES[step.key])) {
        passed.add(step.key);
        if (step.key === "wifi") times.wifi = Date.now();
      }
    }
    status.checklist(steps, passed);
  };

  status.checklist(steps, passed);
  while (passed.size < steps.length && Date.now() < deadline()) {
    const port = await reopen(board, deadline);
    if (!port) break;
    await readLines(port, deadline, () => passed.size === steps.length, (line) => {
      times.heard ??= Date.now();
      onLine(line);
    });
  }

  if (times.heard === null) {
    status.fail("Installed, but received no data from the board. " +
                "Reconnect it, then select Install again.");
  } else if (!passed.has("wifi")) {
    status.fail(`Cannot join Wi-Fi "${config.ssid}". Check the Wi-Fi name and password ` +
                `${NETWORK_PLACE}, then select Install again.`);
  } else if (!passed.has("server")) {
    status.fail(`Cannot reach the server at ${config.serverUrl}. Check the server address ` +
                `${NETWORK_PLACE}, then select Install again.`);
  } else if (steps.length > passed.size) {
    status.fail(`Cannot connect to MQTT at ${config.mqttHost}. ` +
                `Check the MQTT broker ${NETWORK_PLACE}.`);
  } else {
    status.say("Installed. You can unplug the board.");
  }
}

// The board's port, open again after its restart. A board on the chip's own
// USB drops its port while it restarts, and comes back as a new one.
async function reopen(board, deadline) {
  while (Date.now() < deadline()) {
    for (const port of await navigator.serial.getPorts()) {
      if (!board.usbVendorIds.includes(port.getInfo().usbVendorId)) continue;
      try {
        await port.open({ baudRate: LOG_BAUD_RATE });
        return port;
      } catch {
        // Still restarting, or open already.
      }
    }
    await sleep(250);
  }
  return null;
}

// Hands each line the port sends to onLine, until done() or the deadline,
// or until the port is lost.
async function readLines(port, deadline, done, onLine) {
  const reader = port.readable.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  try {
    while (!done()) {
      const left = deadline() - Date.now();
      if (left <= 0) break;
      const chunk = await Promise.race([reader.read(), sleep(left).then(() => null)]);
      if (chunk === null || chunk.done) break;
      pending += decoder.decode(chunk.value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop();
      lines.forEach(onLine);
    }
  } catch {
    // The port was lost: the board restarted again, or was unplugged.
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
    await port.close().catch(() => {});
  }
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
