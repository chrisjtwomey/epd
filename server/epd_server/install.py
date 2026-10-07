"""The install page: a board's firmware and network settings, written over
USB from the browser. It also fills in install-firmware.sh, the same install
from a terminal.

The page is one HTML file and two scripts: ours, and esptool-js, kept here
at a fixed version with its licences. What the page needs from the server
travels inside it as JSON, so it makes no request until a person selects
Install.

A project with a layout of its own draws the page in it instead: an element
with the id ``install``, the config in a script element with the id
``install-config`` (:func:`config_json`, from
:meth:`~epd_server.app.DisplayServer.install_config`), and ``install.js`` as
a module.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "install")
SCRIPTS = ("install.js", "esptool-js-0.7.0.js")
INSTALLER = "install-firmware.sh"


@dataclass(frozen=True)
class InstallBoard:
    """A board the install page offers, and how the browser finds its port."""

    product: str                    # as in client.firmware
    name: str                       # what the page calls it, such as "Dock"
    chip: str                       # as esptool names it: "ESP32", "ESP32-S3"
    usb_vendor_ids: tuple[int, ...]  # the only USB ports the browser lists for it


def server_name(server_url: str) -> str | None:
    """The host of ``server_url`` when it is a name, not an address."""
    host = urlsplit(server_url).hostname if server_url else None
    if not host:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    return None


def board_word(board: InstallBoard) -> str:
    """What a person types for ``board`` in install-firmware.sh: its name,
    lower case, such as ``dock``."""
    return re.sub(r"[^a-z0-9]+", "-", board.name.lower()).strip("-")


def shell_quoted(value: str) -> str:
    """``value`` as one word for a POSIX shell, whatever it holds."""
    return "'" + value.replace("'", "'\\''") + "'"


def installer_script(*, server: str, settings_path: str, wifi_ssid: str,
                     board_server_url: str, mqtt_host: str,
                     boards: list[InstallBoard]) -> str:
    """install-firmware.sh with this server's values filled in: ``server`` as
    the person reached it, and the rest as the install page has them."""
    lines = [
        "|".join((board_word(b), b.product, b.chip.lower().replace("-", ""), b.name,
                  ",".join(f"0x{v:04x}" for v in b.usb_vendor_ids)))
        for b in boards
    ]
    values = {
        "SERVER_HERE": server,
        "SETTINGS_PATH": settings_path,
        "WIFI_SSID": wifi_ssid,
        "BOARD_SERVER_URL": board_server_url,
        "MQTT_HOST": mqtt_host,
        "BOARDS": "\n".join(lines),
    }
    with open(os.path.join(STATIC_DIR, INSTALLER)) as f:
        script = f.read()
    for name, value in values.items():
        placeholder = f"{name}=__{name.removesuffix('_HERE')}__"
        script = script.replace(placeholder, f"{name}={shell_quoted(value)}", 1)
    return script


def config_json(config: dict) -> str:
    """``config`` as JSON to put in a script element. Each ``<`` is escaped,
    so no value can close the element it sits in."""
    return json.dumps(config).replace("<", "\\u003c")


def install_page(config: dict) -> str:
    """The page, carrying ``config`` for its script to read."""
    with open(os.path.join(STATIC_DIR, "install.html")) as f:
        template = f.read()
    return template.replace("{{config}}", config_json(config))
