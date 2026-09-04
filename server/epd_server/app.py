"""The server: serve page PNGs on a schedule, regenerating each one just
before its client wake time.

A project builds its pages and a :class:`~epd_server.source.DataSource`,
hands them to :class:`DisplayServer` with the validated settings, and calls
:meth:`DisplayServer.run`. Everything else — HTTP routes, the
``X-Next-Refresh-Seconds`` / ``X-Next-URL`` headers, the regeneration loop,
the client log relay, signal handling — lives here.

The wire contract with the client is small::

    GET /<page>.png
      200 image/png
      X-Next-Refresh-Seconds: <seconds until the next scheduled wake>
      X-Next-URL: http://host/<the page to fetch at that wake>
      X-Firmware-Version: <version>      only when an update applies
      X-Firmware-URL: http://host/firmware.bin

    GET /firmware.bin
      200 application/octet-stream, Content-Length, x-MD5
      304 when the request's x-ESP32-version is the version held
      404 when the server holds no image

The server is the single source of truth for *when* the client wakes and
*what* it shows. The client does no timezone maths and holds no schedule.
"""
from __future__ import annotations

import io
import logging
import os
import signal
import threading
import time
from datetime import datetime
from typing import Callable, Iterable, Mapping

from flask import Flask, abort, jsonify, make_response, request, send_file
from werkzeug.serving import make_server

from .config import FirmwareSettings, MqttSettings
from .firmware import FirmwareStore, ReleaseWatcher, parse_user_agent, update_applies
from .mqtt import client_log_subscriber
from .page import Page
from .pipeline import regenerate as _regenerate
from .scheduling import Pools, Schedule, TimesSchedule, WakeSchedule, seconds_until
from .source import DataSource

log = logging.getLogger(__name__)


def align_process_timezone(tz) -> None:
    """Make ``time.localtime()`` — and so logging timestamps — use ``tz``.

    Python's logging formats timestamps with ``time.localtime``, which
    follows the process ``TZ``, not any tzinfo the application holds. Call
    this once at startup with the configured zone so log lines and the
    schedule agree. No-op for a tzinfo without an IANA key (e.g. a fixed
    offset), or on platforms without ``time.tzset``.
    """
    key = getattr(tz, "key", None)
    if key and hasattr(time, "tzset"):
        os.environ["TZ"] = key
        time.tzset()


class ServerThread(threading.Thread):
    """Werkzeug's dev server on a daemon thread, with a clean shutdown."""

    def __init__(self, app: Flask, host: str, port: int):
        super().__init__(daemon=True, name="epd-http")
        self.server = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        log.info("Starting http server on %s:%d", *self.server.server_address[:2])
        self.server.serve_forever()

    def shutdown(self):
        log.info("Stopping http server")
        self.server.shutdown()


class DisplayServer:
    """Serve and regenerate a set of pages on a wake schedule.

    Args:
        pages: every page the server offers. Each is served at
            ``/<page.png_filename>`` from ``page.png_path``.
        source: where the pages' content comes from.
        schedule: a :class:`~epd_server.scheduling.WakeSchedule`, from
            :attr:`~epd_server.config.ServerSettings.schedule`; or, for
            convenience, ``(HH:MM:SS, png_filename)`` pairs, which become a
            times schedule of one-image pools. Every filename it can name
            must belong to one of ``pages``.
        tz: the timezone the schedule times are in.
        regen_lead_seconds: regenerate this long before each wake.
        host, port: where to listen.
        mqtt: if given and ``enabled``, relay the client's log topic into
            the ``client`` logger while running.
        mqtt_client_id: the id this server connects to the broker with.
        ingest: routes that accept a JSON object by POST, as
            ``{name: handler}``. ``POST /<name>`` parses the body and calls
            ``handler(doc)``; a ``ValueError`` from the handler is a 400.
        firmware: if given and ``enabled``, offer the image in its directory
            to the boards it is for, and serve it at ``/firmware.bin``.
    """

    def __init__(
        self,
        *,
        pages: Iterable[Page],
        source: DataSource,
        schedule: Schedule | WakeSchedule,
        tz,
        regen_lead_seconds: int = 120,
        host: str = "0.0.0.0",
        port: int = 8080,
        mqtt: MqttSettings | None = None,
        mqtt_client_id: str = "epd-server",
        ingest: Mapping[str, Callable[[dict], None]] | None = None,
        firmware: FirmwareSettings | None = None,
    ):
        self.pages = list(pages)
        self.source = source
        self.tz = tz
        if isinstance(schedule, WakeSchedule):
            self.schedule = schedule
        else:
            if not schedule:
                raise ValueError("DisplayServer needs a non-empty schedule")
            times = list(schedule)
            self.schedule = TimesSchedule(times, Pools({p: [p] for _, p in times}), tz)
        self.regen_lead_seconds = regen_lead_seconds
        self.host = host
        self.port = port
        self.mqtt = mqtt
        self.mqtt_client_id = mqtt_client_id
        self.ingest = dict(ingest or {})
        self.firmware = firmware
        self.firmware_store = FirmwareStore(firmware.dir) if firmware and firmware.enabled else None
        self.release_watcher: ReleaseWatcher | None = None

        if not self.pages:
            raise ValueError("DisplayServer needs at least one page")
        served = {p.png_filename for p in self.pages}
        unknown = sorted(self.schedule.pages() - served)
        if unknown:
            raise ValueError(
                f"display.schedule names {unknown}, but the pages only produce "
                f"{sorted(served)}"
            )
        clash = sorted(set(self.ingest) & served)
        if clash:
            raise ValueError(f"ingest routes {clash} collide with page filenames")

        # Serialises regenerations; a page's PNG is replaced atomically, so
        # readers never wait on it.
        self.regen_lock = threading.Lock()
        self.shutdown_event = threading.Event()
        self.http: ServerThread | None = None
        self.mqtt_client = None

        self.app = self._build_app()

    # ── Scheduling ────────────────────────────────────────────────────────

    def next_wake(self, now: datetime | None = None) -> tuple[int, str]:
        """``(seconds_until_next_wake, png_filename)`` — what the headers carry."""
        if now is None:
            now = datetime.now(tz=self.tz)
        wake_dt, path = self.schedule.next_wake(now=now)
        return seconds_until(now, wake_dt), path

    # ── Regeneration ──────────────────────────────────────────────────────

    def regenerate(self, only: str | None = None, force_refresh: bool = False) -> list[Page]:
        """Regenerate one page (by filename) or all of them, under the lock."""
        with self.regen_lock:
            log.info("Regenerating %s", only or "all pages")
            rendered = _regenerate(self.pages, self.source, only=only, force_refresh=force_refresh)
            log.info("Regeneration complete: %s",
                     ", ".join(p.png_filename for p in rendered) or "nothing rendered")
            return rendered

    # ── HTTP ──────────────────────────────────────────────────────────────

    def _build_app(self) -> Flask:
        app = Flask("epd_server")

        @app.route("/")
        def index():
            seconds, path = self.next_wake()
            image = self.firmware_store.current() if self.firmware_store else None
            return jsonify(
                pages=[p.png_filename for p in self.pages],
                schedule=self.schedule.describe(),
                next_wake_seconds=seconds,
                next_page=path,
                firmware=None if image is None else {
                    "version": image.version, "size": image.size, "md5": image.md5,
                    "product": self.firmware.product if self.firmware else None,
                },
            )

        if self.firmware_store is not None:
            app.add_url_rule("/firmware.bin", endpoint="firmware",
                             view_func=self._serve_firmware)

        for page in self.pages:
            app.add_url_rule(
                "/" + page.png_filename,
                endpoint=page.name,
                view_func=self._make_view(page),
            )
        for name, handler in self.ingest.items():
            app.add_url_rule(
                "/" + name,
                endpoint=f"ingest_{name}",
                view_func=self._make_ingest(name, handler),
                methods=["POST"],
            )
        return app

    def _make_ingest(self, name: str, handler: Callable[[dict], None]):
        def accept():
            doc = request.get_json(silent=True)
            if not isinstance(doc, dict):
                abort(400, "expected a JSON object")
            try:
                handler(doc)
            except ValueError as exc:
                abort(400, str(exc))
            return "", 204
        accept.__name__ = f"ingest_{name}"
        return accept

    def _serve_firmware(self):
        """The image itself. The board asks for this after a page offered it."""
        image = self.firmware_store.current() if self.firmware_store else None
        if image is None:
            abort(404)
        # HTTPUpdate sends the running version, so an image it already has
        # costs one small response instead of a megabyte.
        if request.headers.get("x-ESP32-version") == image.version:
            log.info("%s already runs firmware %s", request.user_agent.string, image.version)
            return "", 304
        with open(image.path, "rb") as f:
            data = f.read()
        log.info("Serving firmware %s (%d bytes) to %s",
                 image.version, image.size, request.user_agent.string)
        rsp = make_response(send_file(
            io.BytesIO(data),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=image.version + ".bin",
        ))
        rsp.headers["Content-Length"] = str(image.size)
        rsp.headers["x-MD5"] = image.md5
        return rsp

    def _firmware_headers(self, rsp) -> None:
        """Add the offer headers when the requesting board has an update."""
        if self.firmware_store is None:
            return
        image = self.firmware_store.current()
        client = parse_user_agent(request.headers.get("User-Agent"))
        if not update_applies(client, image, self.firmware):
            return
        assert image is not None      # update_applies said so
        rsp.headers["X-Firmware-Version"] = image.version
        rsp.headers["X-Firmware-URL"] = request.host_url.rstrip("/") + "/firmware.bin"
        log.info("Offering firmware %s to %s", image.version, request.user_agent.string)

    def _make_view(self, page: Page):
        def serve():
            return self._serve(page)
        serve.__name__ = f"serve_{page.name}"
        return serve

    def _serve(self, page: Page):
        path = page.png_path
        if not os.path.exists(path):
            log.error("%s: no such file exists", path)
            abort(404)

        with open(path, "rb") as f:
            data = f.read()

        seconds, next_path = self.next_wake()
        next_url = request.host_url.rstrip("/") + "/" + next_path.lstrip("/")

        rsp = make_response(send_file(
            io.BytesIO(data),
            mimetype="image/png",
            as_attachment=True,
            download_name=page.png_filename,
        ))
        rsp.headers["X-Next-Refresh-Seconds"] = str(seconds)
        rsp.headers["X-Next-URL"] = next_url
        self._firmware_headers(rsp)
        return rsp

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def run(self, once: bool = False, install_signal_handlers: bool = True) -> None:
        """Regenerate everything, then serve and follow the schedule until stopped.

        ``once=True`` regenerates and returns without starting the HTTP
        server, the log relay, or the loop — handy while iterating on pages.
        """
        self.regenerate()
        if once:
            log.info("once: images generated, not starting the server")
            return

        if self.mqtt is not None and self.mqtt.enabled:
            self.mqtt_client = client_log_subscriber(
                self.mqtt.host, self.mqtt.port, self.mqtt.topic, client_id=self.mqtt_client_id,
            )

        if self.firmware_store is not None and self.firmware.source is not None:
            self.release_watcher = ReleaseWatcher(self.firmware_store, self.firmware.source)
            log.info("Watching %s for releases every %ds", self.firmware.source.github,
                     self.firmware.source.poll_seconds)
            threading.Thread(target=self.release_watcher.run, name="epd-releases",
                             daemon=True).start()

        self.http = ServerThread(self.app, self.host, self.port)
        self.http.start()

        if install_signal_handlers:
            def handle(signum, _frame):
                log.info("Received signal %d, shutting down", signum)
                self.stop()
            signal.signal(signal.SIGTERM, handle)
            signal.signal(signal.SIGINT, handle)

        try:
            self._loop()
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Ask :meth:`run` to return. Safe to call from a signal handler or another thread."""
        self.shutdown_event.set()

    def _loop(self) -> None:
        while not self.shutdown_event.is_set():
            now = datetime.now(tz=self.tz)
            regen_dt, wake_dt, path = self.schedule.next_regen(
                lead_seconds=self.regen_lead_seconds, now=now,
            )
            # Timestamp arithmetic, never `regen_dt - now`: datetime subtraction
            # is naive wall-clock when both sides share a tzinfo and silently
            # drops the hour across a DST transition.
            wait = max(0.0, regen_dt.timestamp() - now.timestamp())
            log.info("Next client wake at %s -> %s", wake_dt.isoformat(), path)
            log.info("Regenerating %s at %s (in %ds)", path, regen_dt.isoformat(), int(wait))
            if self.shutdown_event.wait(wait):
                break
            try:
                self.regenerate(only=path, force_refresh=True)
            except Exception:  # noqa: BLE001 - keep serving; retry at the next slot
                log.exception("Scheduled regeneration failed; will retry at next regen time")

    def _shutdown(self) -> None:
        if self.release_watcher is not None:
            self.release_watcher.stop()
            self.release_watcher = None
        if self.http is not None:
            self.http.shutdown()
            self.http = None
        if self.mqtt_client is not None:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.mqtt_client = None
        log.info("Exited")
