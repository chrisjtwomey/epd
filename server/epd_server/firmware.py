"""Firmware images: what the server holds, and which client it applies to.

The board sends its identity on every page fetch::

    inkplate10-weather-cal/v1.5.1 (Inkplate10)

so the server can answer "is there a newer image for you?" without the board
knowing anything about releases. When there is, the page response carries
``X-Firmware-Version`` and ``X-Firmware-URL``, and the board fetches the
image after it has drawn.

A :class:`FirmwareStore` is a directory of ``<version>.bin``. The version is
the filename, so an image built by hand works the moment it is copied in::

    server/firmware/v1.6.0.bin
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

# name/version, then an optional parenthesised device: the shape
# buildUserAgent() writes in the client library.
_USER_AGENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)/(\S+)(?:\s+\(([^)]*)\))?\s*$")

# What `git describe` gives at a tag, and nothing more: v1.5.1 or 1.5.1.
# A build past the tag adds -3-gab12cd4, a dirty tree adds -dirty, and a
# repository with no tags gives "dev". None of those is a release.
_CLEAN_TAG = re.compile(r"^v?\d+\.\d+(\.\d+)?$")

# A version has to be a filename, since the filename is where it is kept.
_VERSION_CHARS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


@dataclass(frozen=True)
class ClientId:
    """A board's own account of itself, from its User-Agent."""

    name: str
    version: str
    device: str = ""


@dataclass(frozen=True)
class FirmwareImage:
    """One image in the store."""

    version: str
    path: str
    size: int
    md5: str


def parse_user_agent(ua: str | None) -> ClientId | None:
    """``"weather-cal/v1.5.1 (Inkplate10)"`` -> :class:`ClientId`, else ``None``."""
    if not ua:
        return None
    match = _USER_AGENT.match(ua.strip())
    if not match:
        return None
    name, version, device = match.groups()
    return ClientId(name=name, version=version, device=(device or "").strip())


def is_clean_tag(version: str) -> bool:
    """True for a version built from a tag, false for a developer build."""
    return bool(version) and bool(_CLEAN_TAG.match(version))


def update_applies(client: ClientId | None, image: FirmwareImage | None, settings) -> bool:
    """Whether ``image`` is an update for ``client``.

    ``settings`` is a :class:`~epd_server.config.FirmwareSettings`. Developer
    builds are left alone unless ``offer_dev_builds`` says otherwise, so a
    board on the bench is not flashed back to the last release.
    """
    if settings is None or not settings.enabled or image is None or client is None:
        return False
    if client.name != settings.product:
        return False
    if not settings.offer_dev_builds and not is_clean_tag(client.version):
        return False
    return client.version != image.version


class FirmwareStore:
    """A directory of ``<version>.bin``. The newest file is the current image.

    Nothing is held open between calls, so an image copied in while the
    server runs is offered at the next fetch. The md5 is computed once per
    file and kept while its size and modification time are unchanged.
    """

    def __init__(self, directory: str):
        self.dir = directory
        self._cache: tuple[tuple, FirmwareImage] | None = None

    def current(self) -> FirmwareImage | None:
        """The image to offer, or ``None`` when the directory holds none."""
        path = self._newest_bin()
        if path is None:
            return None
        stat = os.stat(path)
        key = (path, stat.st_mtime_ns, stat.st_size)
        if self._cache and self._cache[0] == key:
            return self._cache[1]
        image = FirmwareImage(
            version=os.path.basename(path)[: -len(".bin")],
            path=path,
            size=stat.st_size,
            md5=_md5_of(path),
        )
        self._cache = (key, image)
        return image

    def put(self, version: str, data: bytes) -> FirmwareImage:
        """Store ``data`` as ``<version>.bin`` and remove any older image."""
        if not _VERSION_CHARS.match(version or ""):
            raise ValueError(f"version {version!r} cannot be a filename")
        if not data.startswith(b"\xe9"):
            raise ValueError("not an ESP32 image: the first byte is not the 0xE9 magic")
        os.makedirs(self.dir, exist_ok=True)
        path = os.path.join(self.dir, version + ".bin")
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        for old in self._bins():
            if old != path:
                os.remove(old)
        self._cache = None
        log.info("Stored firmware %s (%d bytes)", version, len(data))
        image = self.current()
        assert image is not None      # just written
        return image

    def _bins(self) -> list[str]:
        try:
            names = os.listdir(self.dir)
        except OSError:
            return []
        return [os.path.join(self.dir, n) for n in names if n.endswith(".bin")]

    def _newest_bin(self) -> str | None:
        usable = []
        for path in self._bins():
            version = os.path.basename(path)[: -len(".bin")]
            if _VERSION_CHARS.match(version):
                usable.append(path)
            else:
                log.warning("%s: the filename is the version, so rename it to <version>.bin", path)
        if not usable:
            return None
        return max(usable, key=lambda p: os.stat(p).st_mtime_ns)


def _md5_of(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()
