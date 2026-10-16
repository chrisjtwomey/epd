"""install-firmware.sh, run by a real shell against a test server, with a
stand-in esptool and a file in place of the board's port."""
import os
import pty
import re
import subprocess
import urllib.request

import pytest
from flask import redirect, request

from epd_server.app import ServerThread
from epd_server.config import FirmwareSettings, MqttSettings, NetworkSettings
from epd_server.install import INSTALLER, STATIC_DIR, InstallBoard
from epd_server.network import network_settings_file

from .test_app import BIN, PNG, make

NETWORK = NetworkSettings("http://epd.local:8080", "Home's \"Wi-Fi\" $(x)", "correct horse",
                          "epd.local")
MQTT = MqttSettings(True, "mosquitto", 1883, "mqtt/epd")
DOCK = InstallBoard("my-dock", "Dock", "ESP32-S3", (0x303A,))
DISPLAY = InstallBoard("my-display", "Display", "ESP32", (0x1A86,))
STARTED = ["... wifi connected in 1100 ms: 10.0.0.9",
           "... reached the server at http://epd.local:8080/today.png",
           "... connected to MQTT broker epd.local:1883"]

TOKEN = "t0ken"
PASSWORD = "horse & battery=100%"

FAKE_ESPTOOL = r"""#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_DIR/calls"
for arg in "$@"; do
    case $arg in *.bin) cp "$arg" "$FAKE_DIR/$(basename "$arg")" ;; esac
done
if [ -n "${FAKE_SAYS:-}" ]; then printf '%s\n' "$FAKE_SAYS"; exit 2; fi
printf 'Serial port %s:\n' "$FAKE_PORT"
"""


def sign_in_in_front(app, too_many):
    """A stand-in for a project's sign-in in front of /network.bin: it takes
    TOKEN, or the cookie that its form at /web/login sets for PASSWORD. With
    ``too_many``, the form answers 429, with that Retry-After when it is not
    "". Returns the passwords posted to the form."""
    posted = []

    @app.before_request
    def signed_in_only():
        if request.path == "/network.bin" and request.cookies.get("signed-in") != "yes" \
                and request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return "", 401
        return None

    @app.post("/web/login")
    def sign_in():
        posted.append(request.form.get("password"))
        if too_many is not None:
            return "", 429, {"Retry-After": too_many} if too_many else {}
        if request.form.get("password") != PASSWORD:
            return "", 401
        rsp = redirect("/web/", 303)
        rsp.set_cookie("signed-in", "yes", httponly=True)
        return rsp

    return posted


@pytest.fixture
def serve(tmp_path):
    """Starts a test server and returns its address. With ``signed_in``, a
    sign-in stands in front of /network.bin, and the list of passwords
    posted to it is ``posted``."""
    fw = tmp_path / "fw"
    for product in ("my-dock", "my-display"):
        (fw / product).mkdir(parents=True)
        (fw / product / "v0.3.0.bin").write_bytes(BIN)
    (fw / "my-dock" / "v0.3.0.merged.bin").write_bytes(BIN + b"merged")
    (tmp_path / "today.png").write_bytes(PNG)
    (tmp_path / "hourly.png").write_bytes(PNG)
    threads = []

    def start(network=NETWORK, install_url=None, login_url=None, signed_in=False,
              too_many=None):
        firmware = FirmwareSettings(enabled=True, dir=str(fw), product="my-dock",
                                    offer_dev_builds=False, products=("my-dock", "my-display"))
        server = make(tmp_path, firmware=firmware, network=network, mqtt=MQTT,
                      install_boards=[DOCK, DISPLAY], settings_url="settings",
                      install_url=install_url, login_url=login_url)
        if signed_in:
            start.posted = sign_in_in_front(server.app, too_many)
        http = ServerThread(server.app, "127.0.0.1", 0, timeout_s=2)
        http.start()
        threads.append(http)
        return f"http://127.0.0.1:{http.server.server_port}"

    yield start
    for http in threads:
        http.shutdown()


def run(tmp_path, server, *args, says=None, port_lines=(), env=None, typed=None):
    """Downloads the script from ``server`` and runs it with ``args``. With
    ``typed``, its stdin is a terminal, and ``typed`` is the line typed there."""
    script = tmp_path / INSTALLER
    script.write_bytes(urllib.request.urlopen(f"{server}/{INSTALLER}", timeout=5).read())
    fake = tmp_path / "fake"
    fake.mkdir(exist_ok=True)
    esptool = fake / "esptool"
    esptool.write_text(FAKE_ESPTOOL)
    esptool.chmod(0o755)
    port = tmp_path / "port"
    port.write_text("".join(f"{line}\n" for line in port_lines))
    locale = {k: v for k, v in os.environ.items() if k in ("LANG", "LC_ALL", "LC_CTYPE")}
    temp = tmp_path / "temp"
    temp.mkdir(exist_ok=True)
    environ = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), **locale,
               "XDG_CACHE_HOME": str(tmp_path / ".cache"), "ESPTOOL": str(esptool),
               "FAKE_DIR": str(fake), "FAKE_PORT": str(port), "TMPDIR": str(temp),
               **(env or {})}
    if says:
        environ["FAKE_SAYS"] = says
    if typed is None:
        return subprocess.run(["sh", str(script), *args], env=environ, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=30)
    keyboard, terminal = pty.openpty()
    try:
        os.write(keyboard, typed.encode() + b"\n")
        return subprocess.run(["sh", str(script), *args], env=environ, stdin=terminal,
                              capture_output=True, text=True, timeout=30)
    finally:
        os.close(terminal)
        os.close(keyboard)


def calls(tmp_path) -> list[str]:
    path = tmp_path / "fake" / "calls"
    return path.read_text().splitlines() if path.exists() else []


def test_the_script_carries_this_servers_values(tmp_path, serve):
    server = serve(login_url="web/login")

    rsp = urllib.request.urlopen(f"{server}/{INSTALLER}", timeout=5)
    script = rsp.read().decode()

    assert rsp.headers["Content-Type"].startswith("text/plain")
    assert rsp.headers["Cache-Control"] == "no-store"
    assert "=__" not in script
    assert subprocess.run(["sh", "-n", "-c", script]).returncode == 0
    values = script[script.index("# values"):script.index("# end of values")]
    shown = subprocess.run(
        ["sh", "-c", values + 'printf "%s\\n" "$SERVER_HERE" "$SETTINGS_PATH" "$LOGIN_PATH" '
         '"$WIFI_SSID" "$BOARD_SERVER_URL" "$MQTT_HOST" "$BOARDS"'],
        capture_output=True, text=True).stdout.splitlines()
    assert shown == [server, "settings", "web/login", "Home's \"Wi-Fi\" $(x)",
                     "http://epd.local:8080",
                     "epd.local", "dock|my-dock|esp32s3|Dock|0x303a",
                     "display|my-display|esp32|Display|0x1a86"]


@pytest.mark.parametrize("args", [(), ("nope",), ("dock", "display")])
def test_a_missing_or_unknown_board_lists_the_boards(tmp_path, serve, args):
    result = run(tmp_path, serve(), *args)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "Install firmware on a board connected by USB.",
        "  sh install-firmware.sh dock            (firmware and network settings)",
        "  sh install-firmware.sh dock-network    (network settings only)",
        "Boards: dock, display",
    ]
    assert calls(tmp_path) == []


def test_an_install_writes_both_files_then_follows_the_board(tmp_path, serve):
    result = run(tmp_path, serve(), "dock", port_lines=STARTED)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "Installing on the Dock… Keep the board connected.",
        "Restarting the board…",
        "✓ Joined Wi-Fi",
        "✓ Reached the server",
        "✓ Connected to MQTT",
        "Installed. You can unplug the board.",
    ]
    cache = tmp_path / ".cache" / "epd"
    assert calls(tmp_path) == [
        f"--chip esp32s3 --port-filter vid=0x303a --baud 460800 write-flash 0x0 {cache}/firmware.bin",
        f"--chip esp32s3 --port-filter vid=0x303a --baud 460800 write-flash 0x9000 {cache}/network.bin",
    ]
    assert (tmp_path / "fake" / "firmware.bin").read_bytes() == BIN + b"merged"
    assert (tmp_path / "fake" / "network.bin").read_bytes() == network_settings_file(
        NETWORK, MQTT, product="my-dock", first_page="today.png")


def test_network_only_writes_the_settings_alone_through_the_given_port(tmp_path, serve):
    port = tmp_path / "port"
    result = run(tmp_path, serve(), "dock-network", port_lines=STARTED, env={"PORT": str(port)})

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "Installed. You can unplug the board."
    assert calls(tmp_path) == [f"--chip esp32s3 --port {port} --baud 460800 write-flash "
                               f"0x9000 {tmp_path}/.cache/epd/network.bin"]


def test_a_board_with_no_firmware_yet(tmp_path, serve):
    result = run(tmp_path, serve(), "display")

    assert result.returncode == 1
    assert result.stderr.strip() == ("No firmware to install for the Display yet. "
                                     "It appears once the server has built it.")
    assert calls(tmp_path) == []


def test_network_settings_not_set_are_named_as_in_settings(tmp_path, serve):
    server = serve(network=NetworkSettings(wifi_ssid="Home"))

    result = run(tmp_path, server, "dock-network")

    assert result.returncode == 1
    assert result.stderr.strip() == ("Missing: Server address, Wi-Fi password, MQTT broker. "
                                     f"Add them in Settings: {server}/settings")


def test_network_settings_not_set_are_named_as_on_the_install_page_that_holds_them(tmp_path,
                                                                                  serve):
    server = serve(network=NetworkSettings(wifi_ssid="Home"), install_url="web/install")

    result = run(tmp_path, server, "dock-network")

    assert result.returncode == 1
    assert result.stderr.strip() == ("Missing: Server address, Wi-Fi password, MQTT broker. "
                                     f"Add them on the install page: {server}/web/install")


@pytest.mark.parametrize("install_url, place", [(None, "in Settings"),
                                                ("web/install", "on the install page")])
def test_a_fault_after_the_install_says_where_the_network_settings_are(tmp_path, serve,
                                                                       install_url, place):
    script = urllib.request.urlopen(f"{serve(install_url=install_url)}/{INSTALLER}",
                                    timeout=5).read().decode()
    functions = script[:script.index("[ $# -eq 1 ] || usage")]

    said = subprocess.run(["sh", "-c", functions + "network_place"], capture_output=True,
                          text=True, timeout=10)

    assert said.stdout == place
    assert script.count("$(network_place)") == 3


def test_a_server_with_a_sign_in_takes_the_password_typed(tmp_path, serve):
    server = serve(login_url="web/login", signed_in=True)

    result = run(tmp_path, server, "dock", port_lines=STARTED, typed=PASSWORD)

    assert result.returncode == 0, result.stderr
    assert result.stderr == "Server password: \n"
    assert result.stdout.splitlines()[-1] == "Installed. You can unplug the board."
    assert serve.posted == [PASSWORD]
    assert (tmp_path / "fake" / "network.bin").read_bytes() == network_settings_file(
        NETWORK, MQTT, product="my-dock", first_page="today.png")
    assert os.listdir(tmp_path / "temp") == []


@pytest.mark.parametrize("typed, text", [("horse", "Wrong password. Try again."),
                                         ("", "No password entered. Try again.")])
def test_a_wrong_password_stops_the_install(tmp_path, serve, typed, text):
    server = serve(login_url="web/login", signed_in=True)

    result = run(tmp_path, server, "dock", typed=typed)

    assert result.returncode == 1
    assert result.stderr == f"Server password: \n{text}\n"
    assert calls(tmp_path) == []
    assert os.listdir(tmp_path / "temp") == []


@pytest.mark.parametrize("retry_after, wait", [("840", "in 14 minutes"), ("30", "in 1 minute"),
                                               ("", "later")])
def test_too_many_tries_says_when_to_try_again(tmp_path, serve, retry_after, wait):
    server = serve(login_url="web/login", signed_in=True, too_many=retry_after)

    result = run(tmp_path, server, "dock", typed=PASSWORD)

    assert result.returncode == 1
    assert result.stderr.splitlines()[-1] == f"Too many tries. Try again {wait}."


def test_the_token_signs_in_without_the_password(tmp_path, serve):
    server = serve(login_url="web/login", signed_in=True)

    result = run(tmp_path, server, "dock", port_lines=STARTED, env={"TOKEN": TOKEN},
                 typed=PASSWORD)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert serve.posted == []
    assert (tmp_path / "fake" / "network.bin").read_bytes() == network_settings_file(
        NETWORK, MQTT, product="my-dock", first_page="today.png")


def test_a_refused_token_stops_the_install(tmp_path, serve):
    server = serve(login_url="web/login", signed_in=True)

    result = run(tmp_path, server, "dock", env={"TOKEN": "old"}, typed=PASSWORD)

    assert result.returncode == 1
    assert result.stderr.strip() == "Access token refused. Copy it from Settings, then try again."
    assert serve.posted == []
    assert calls(tmp_path) == []


@pytest.mark.parametrize("login_url, typed", [("web/login", None), (None, PASSWORD)])
def test_a_sign_in_the_script_cannot_do_names_the_token(tmp_path, serve, login_url, typed):
    server = serve(login_url=login_url, signed_in=True)

    result = run(tmp_path, server, "dock", typed=typed)

    assert result.returncode == 1
    assert result.stderr.strip() == ("Sign-in needed. Set TOKEN to the access token from "
                                     "Settings, then try again.")
    assert serve.posted == []


@pytest.mark.parametrize("env, typed, secret", [({}, PASSWORD, PASSWORD),
                                                 ({"TOKEN": TOKEN}, None, TOKEN)])
def test_no_secret_goes_on_curls_command_line(tmp_path, serve, env, typed, secret):
    server = serve(login_url="web/login", signed_in=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    real = subprocess.run(["sh", "-c", "command -v curl"], capture_output=True,
                          text=True).stdout.strip()
    logged = tmp_path / "curl-args"
    curl = bin_dir / "curl"
    curl.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{logged}"\nexec "{real}" "$@"\n')
    curl.chmod(0o755)

    result = run(tmp_path, server, "dock-network", port_lines=STARTED, typed=typed,
                 env={"PATH": f"{bin_dir}:{os.environ['PATH']}", **env})

    assert result.returncode == 0, result.stderr
    assert "network.bin" in logged.read_text()
    assert secret not in logged.read_text()


def test_a_server_that_does_not_answer(tmp_path, serve):
    result = run(tmp_path, serve(), "dock", env={"SERVER": "http://127.0.0.1:1"})

    assert result.returncode == 1
    assert result.stderr.strip() == ("Cannot reach the server at http://127.0.0.1:1. "
                                     "Check that it is running, then try again.")


@pytest.mark.parametrize("says, text", [
    ("Found 0 serial ports...",
     "No board found. Connect it with a USB cable, then try again."),
    ("A fatal error occurred: This chip is ESP32, not ESP32-S3. Wrong --chip argument?",
     "Wrong board: this one is not the Dock. Connect the Dock, then try again."),
    ("Could not open /dev/x, the port is busy or doesn't exist.",
     "Board in use by another app. Close that app, then try again."),
    ("Failed to connect to ESP32-S3: No serial data received.",
     "Board not responding. Hold BOOT while you press RST, then try again."),
    ("Something else went wrong.",
     "Install failed. Reconnect the board, then try again.\n"
     "Log: ~/.cache/epd/install-firmware.log"),
])
def test_an_esptool_failure_says_what_to_do(tmp_path, serve, says, text):
    result = run(tmp_path, serve(), "dock", says=says)

    assert result.returncode == 1
    assert result.stderr.strip() == text
    assert len(calls(tmp_path)) == 1


def test_a_port_that_is_not_there_is_no_board(tmp_path, serve):
    result = run(tmp_path, serve(), "dock", env={"PORT": str(tmp_path / "gone")})

    assert result.returncode == 1
    assert result.stderr.strip() == "No board found. Connect it with a USB cable, then try again."
    assert calls(tmp_path) == []


def test_the_script_waits_for_the_same_lines_as_the_page():
    with open(os.path.join(STATIC_DIR, "install.js")) as f:
        page = re.findall(r'"([^"]+)"', re.search(r"const LINES = \{(.*?)\};", f.read(), re.S)[1])
    with open(os.path.join(STATIC_DIR, INSTALLER)) as f:
        script = re.findall(r'passed "([^"]+)"', f.read())

    assert script == page
