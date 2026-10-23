"""The routes that put firmware and network settings on a board over USB:
``/install``, its scripts, ``install-firmware.sh``, and ``/network.bin``.

:class:`~epd_server.app.DisplayServer` makes one :class:`InstallRoutes` and
registers its routes; the page itself and the script are built in
:mod:`epd_server.install`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from flask import Flask, abort, make_response, request, send_from_directory

from .config import FirmwareSettings, MqttSettings, NetworkSettings
from .install import (
    INSTALLER,
    SCRIPTS,
    STATIC_DIR,
    InstallBoard,
    install_page,
    installer_script,
    server_name,
)
from .network import STORE_OFFSET, network_settings_file
from .offers import FirmwareOffers
from .responses import download, text

log = logging.getLogger(__name__)


class InstallRoutes:
    """The install page and the files it writes. ``network`` is read at each
    request, so a project can replace its server's network settings while it
    runs."""

    def __init__(self, *, firmware: FirmwareSettings | None,
                 network: Callable[[], NetworkSettings | None], mqtt: MqttSettings | None,
                 offers: FirmwareOffers, boards: Iterable[InstallBoard], https_port: int,
                 first_page: str, settings_url: str | None, install_url: str | None,
                 login_url: str | None):
        self.firmware = firmware
        self.network = network
        self.mqtt = mqtt
        self.offers = offers
        self.boards = list(boards)
        self.https_port = https_port
        self.first_page = first_page
        self.settings_url = settings_url
        self.install_url = install_url
        self.login_url = login_url

    def register(self, app: Flask) -> None:
        if self.network() is not None and self.firmware is not None:
            app.add_url_rule("/network.bin", endpoint="network", view_func=self._serve_network)
        if self.boards:
            app.add_url_rule("/install", endpoint="install", view_func=self._serve_install)
            app.add_url_rule("/install/<name>", endpoint="install_script",
                             view_func=self._serve_install_script)
            app.add_url_rule("/" + INSTALLER, endpoint="installer",
                             view_func=self._serve_installer)

    def config(self, root: str = "", network_here: bool = False) -> dict:
        """What the install page's script needs to know; see
        :meth:`~epd_server.app.DisplayServer.install_config`."""
        network = self.network()
        assert network is not None   # checked by DisplayServer
        return {
            "root": root,
            "boards": [{
                "product": b.product,
                "name": b.name,
                "chip": b.chip,
                "usbVendorIds": list(b.usb_vendor_ids),
                "version": self.offers.installable_version(b.product),
            } for b in self.boards],
            "missing": network.missing(self.mqtt),
            "ssid": network.wifi_ssid,
            "serverUrl": network.server_url,
            "mqttHost": network.mqtt_host if self.mqtt and self.mqtt.enabled else None,
            "httpsPort": self.https_port,
            "serverName": server_name(network.server_url),
            "settingsUrl": root + self.settings_url if self.settings_url else None,
            "networkUrl": root + self.install_url if self.install_url else None,
            "networkHere": network_here,
            "storeOffset": STORE_OFFSET,
        }

    def _serve_install(self):
        rsp = make_response(install_page(self.config()))
        rsp.headers["Cache-Control"] = "no-store"
        return rsp

    def _serve_installer(self):
        """install-firmware.sh, which downloads from this server as the person
        reached it."""
        network = self.network()
        assert network is not None   # checked by DisplayServer
        script = installer_script(
            server=request.host_url.rstrip("/"),
            settings_path=self.settings_url or "",
            network_path=self.install_url or "",
            login_path=self.login_url or "",
            wifi_ssid=network.wifi_ssid,
            board_server_url=network.server_url,
            mqtt_host=network.mqtt_host if self.mqtt and self.mqtt.enabled else "",
            boards=self.boards,
        )
        rsp = make_response(script)
        rsp.mimetype = "text/plain"
        rsp.headers["Cache-Control"] = "no-store"
        return rsp

    def _serve_install_script(self, name: str):
        if name not in SCRIPTS:
            abort(404)
        return send_from_directory(STATIC_DIR, name, mimetype="text/javascript")

    def _serve_network(self):
        """A product's network settings, as the board's settings store."""
        network = self.network()
        assert self.firmware is not None and network is not None
        product = request.args.get("product") or self.firmware.product
        if product not in self.firmware.names():
            return text(404, f"No product named {product}.")
        missing = network.missing(self.mqtt)
        if missing:
            log.warning("Network settings for %s asked for, but %s not set",
                        product, ", ".join(missing))
            return text(409, f"Network settings not set: {', '.join(missing)}.")
        data = network_settings_file(network, self.mqtt, product=product,
                                     first_page=self.first_page)
        log.info("Serving the network settings of %s to %s", product,
                 request.user_agent.string)
        rsp = download(data, f"{product}-network.bin")
        rsp.headers["Content-Length"] = str(len(data))
        rsp.headers["Cache-Control"] = "no-store"
        return rsp
