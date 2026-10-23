"""The firmware a server offers its boards: which image each one should run,
the headers that offer it on any response, and the routes that serve it.

:class:`~epd_server.app.DisplayServer` makes one :class:`FirmwareOffers`
from its ``firmware`` settings and registers its routes; the wire contract is
in :mod:`epd_server.app`.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from flask import Flask, abort, request

from .board_keys import content_digest
from .compat import version_order
from .config import FirmwareSettings
from .firmware import FirmwareImage, FirmwareStore, client_from_headers, update_applies
from .headers import Wire
from .responses import download, text

log = logging.getLogger(__name__)


def _image_response(image: FirmwareImage, download_name: str):
    """A firmware image as a download, with the md5 an ESP32 checks it by."""
    with open(image.path, "rb") as f:
        data = f.read()
    rsp = download(data, download_name)
    rsp.headers["Content-Length"] = str(image.size)
    rsp.headers["x-MD5"] = image.md5
    rsp.headers["Content-Digest"] = content_digest(data)
    return rsp


class FirmwareOffers:
    """The images a server holds for each product, and which one a board of
    it is offered: with ``version_gate``, the newest that can work with
    ``server_version``; without, the newest file."""

    def __init__(self, firmware: FirmwareSettings | None, *, version_gate: bool,
                 server_version: str, wire: Wire):
        self.firmware = firmware
        self.version_gate = version_gate
        self.server_version = server_version
        self.wire = wire
        self.stores = ({p: FirmwareStore(firmware.dir_for(p)) for p in firmware.names()}
                       if firmware and firmware.enabled else {})
        # The default product's: what the release watcher fills and / reports.
        self.store = self.stores.get(firmware.product) if firmware else None

    def register(self, app: Flask) -> None:
        if self.store is not None:
            app.add_url_rule("/firmware.bin", endpoint="firmware", view_func=self._serve_firmware)
            app.add_url_rule("/firmware.merged.bin", endpoint="firmware_merged",
                             view_func=self._serve_merged)

    def offer(self, product: str) -> FirmwareImage | None:
        """The image a board of ``product`` should run, before asking whether
        it runs it already."""
        store = self.stores.get(product)
        if store is None:
            return None
        return store.newest_compatible(self.server_version) if self.version_gate else store.current()

    def merged_offer(self, product: str) -> tuple[FirmwareImage | None, FirmwareImage | None]:
        """The image a product is offered over the air, and its merged image."""
        store = self.stores.get(product)
        image = self.offer(product) if store is not None else None
        if store is None or image is None:
            return image, None
        return image, store.merged(image.version)

    def installable_version(self, product: str) -> str | None:
        """The version ``/firmware.merged.bin`` would serve ``product``, if any."""
        _, merged = self.merged_offer(product)
        return merged.version if merged is not None else None

    def add_headers(self, rsp) -> None:
        """Add the offer headers when the requesting board has an update."""
        if not self.stores or request.endpoint == "firmware":
            return
        firmware = self.firmware
        assert firmware is not None   # the stores exist only when it does
        client = client_from_headers(request.headers.get(self.wire.device),
                                     request.headers.get(self.wire.device_version))
        image = self.offer(client.name) if client is not None else None
        if not update_applies(client, image, firmware):
            return
        assert image is not None and client is not None   # update_applies said so
        url = self._url(image, client.name)
        # The version travels with the URL because the board checks it against
        # the one it rolled back from, before it downloads anything.
        rsp.headers[self.wire.firmware_version] = image.version
        rsp.headers[self.wire.firmware_url] = url
        older = version_order(image.version) or (0, 0, 0, 0)
        if older < (version_order(client.version) or (0, 0, 0, 0)):
            log.warning("Offering %s %s an older firmware, %s: this server is %s",
                        client.name, client.version, image.version, self.server_version)
        else:
            log.info("Offering firmware %s to %s %s", image.version, client.name, client.version)

    def _url(self, image: FirmwareImage, product: str) -> str:
        url = request.host_url.rstrip("/") + "/firmware.bin"
        if self.firmware is not None and self.firmware.products:
            url += "?" + urlencode({"product": product, "version": image.version})
        return url

    def _serve_firmware(self):
        """The image itself. The board asks for this after a response offered it."""
        assert self.firmware is not None   # the route exists only when it does
        product = request.args.get("product") or self.firmware.product
        version = request.args.get("version")
        store = self.stores.get(product)
        if store is None:
            abort(404)
        image = store.image(version) if version else self.offer(product)
        if image is None:
            abort(404)
        # The board sends the version it runs, so an image it already has
        # costs one small response instead of a megabyte.
        if request.headers.get("x-ESP32-version") == image.version:
            log.info("%s already runs firmware %s", request.user_agent.string, image.version)
            return "", 304
        log.info("Serving firmware %s (%d bytes) to %s",
                 image.version, image.size, request.user_agent.string)
        return _image_response(image, image.version + ".bin")

    def _serve_merged(self):
        """The merged image of the version a product is offered over the air,
        so a board flashed with it is not updated straight after."""
        assert self.firmware is not None   # the route exists only when it does
        product = request.args.get("product") or self.firmware.product
        image, merged = self.merged_offer(product)
        if merged is None:
            if image is not None:
                log.warning("No merged image of %s %s", product, image.version)
            return text(404, f"No firmware to install for {product} yet.")
        log.info("Serving the merged image of %s %s (%d bytes) to %s",
                 product, merged.version, merged.size, request.user_agent.string)
        return _image_response(merged, f"{product}-{merged.version}.merged.bin")
