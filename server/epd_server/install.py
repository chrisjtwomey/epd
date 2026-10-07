"""The install page: a board's firmware and network settings, written over
USB from the browser.

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
from dataclasses import dataclass
from urllib.parse import urlsplit

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "install")
SCRIPTS = ("install.js", "esptool-js-0.7.0.js")


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


def config_json(config: dict) -> str:
    """``config`` as JSON to put in a script element. Each ``<`` is escaped,
    so no value can close the element it sits in."""
    return json.dumps(config).replace("<", "\\u003c")


def install_page(config: dict) -> str:
    """The page, carrying ``config`` for its script to read."""
    with open(os.path.join(STATIC_DIR, "install.html")) as f:
        template = f.read()
    return template.replace("{{config}}", config_json(config))
