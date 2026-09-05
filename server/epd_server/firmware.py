"""Firmware images: what the server holds, and which client it applies to.

The board sends its identity on every page fetch::

    my-display/v1.2.0 (Inkplate10)

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
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
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
    """``"my-display/v1.2.0 (Inkplate10)"`` -> :class:`ClientId`, else ``None``."""
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


class ReleaseWatcher:
    """Keep a :class:`FirmwareStore` filled from a repository's releases.

    Asks GitHub for the latest release, and when its tag is not the version
    already held, downloads the named asset and stores it. The ``fetch``
    callable is injected so the whole loop is testable without a network::

        fetch(url, headers) -> (status, headers, body)

    A private repository needs a token. Its asset is then fetched from the
    API's own asset URL, because ``browser_download_url`` is not authorised.
    """

    #: How long to wait after a failure, before doubling up to the poll interval.
    FIRST_RETRY_SECONDS = 60

    def __init__(self, store: FirmwareStore, source, fetch=None, stop_event=None):
        self.store = store
        self.source = source
        self.fetch = fetch or _fetch_url
        self.stop_event = stop_event or threading.Event()
        self.etag: str | None = None

    @property
    def releases_url(self) -> str:
        return f"https://api.github.com/repos/{self.source.github}/releases/latest"

    def _headers(self, accept: str) -> dict:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if self.source.token:
            headers["Authorization"] = f"Bearer {self.source.token}"
        return headers

    def check_once(self) -> FirmwareImage | None:
        """Fetch the latest release and store its asset. Returns what was stored."""
        headers = self._headers("application/vnd.github+json")
        if self.etag:
            headers["If-None-Match"] = self.etag
        status, response_headers, body = self.fetch(self.releases_url, headers)

        if status == 304:
            log.debug("No new release for %s", self.source.github)
            return None
        if status != 200:
            raise RuntimeError(f"GitHub answered {status} for {self.releases_url}")
        self.etag = response_headers.get("ETag")

        release = json.loads(body)
        tag = str(release.get("tag_name") or "").strip()
        if not tag:
            raise RuntimeError("the latest release has no tag_name")

        held = self.store.current()
        if held is not None and held.version == tag:
            log.debug("Release %s is already held", tag)
            return None

        asset = next((a for a in release.get("assets", [])
                      if a.get("name") == self.source.asset), None)
        if asset is None:
            raise RuntimeError(f"release {tag} has no asset named {self.source.asset}")

        data = self._download(asset)
        expected = asset.get("size")
        if expected is not None and len(data) != expected:
            raise RuntimeError(f"{self.source.asset} is {len(data)} bytes, expected {expected}")

        log.info("New release %s for %s", tag, self.source.github)
        return self.store.put(tag, data)

    def _download(self, asset: dict) -> bytes:
        # The browser URL is a redirect to unauthenticated storage, so a
        # private repository has to go through the API's asset URL instead.
        if self.source.token:
            url = asset["url"]
        else:
            url = asset.get("browser_download_url") or asset["url"]
        status, _, body = self.fetch(url, self._headers("application/octet-stream"))
        if status != 200:
            raise RuntimeError(f"GitHub answered {status} for {url}")
        return body

    def run(self) -> None:
        """Check now, then every ``poll_seconds`` until the stop event is set."""
        wait_after_failure = self.FIRST_RETRY_SECONDS
        while not self.stop_event.is_set():
            wait = self.source.poll_seconds
            try:
                self.check_once()
                wait_after_failure = self.FIRST_RETRY_SECONDS
            except Exception as exc:      # noqa: BLE001 - a release check must not stop the server
                # Retry sooner than the poll interval at first, so a network
                # that was down at startup is not an hour of no images.
                wait = min(self.source.poll_seconds, wait_after_failure)
                wait_after_failure = min(self.source.poll_seconds, wait_after_failure * 2)
                log.warning("Release check failed (%s); trying again in %ds", exc, wait)
            if self.stop_event.wait(wait):
                return

    def stop(self) -> None:
        self.stop_event.set()


def _fetch_url(url: str, headers: dict):
    """The default ``fetch``: one GET, following redirects, never raising on 304."""
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
