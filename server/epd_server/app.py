"""The server: serve page PNGs on a schedule, regenerating each one just
before its client wake time.

A project builds its pages and a :class:`~epd_server.source.DataSource`,
hands them to :class:`DisplayServer` with the validated settings, and calls
:meth:`DisplayServer.run`. Everything else — HTTP routes, the schedule and
identity headers, the regeneration loop, the client log relay, signal
handling — lives here.

The wire contract with the client is small. Every name below is written with
the default prefix; a project sets its own, and :mod:`epd_server.headers`
builds the names from it::

    GET /<page>.png
      EPD-Device: <product>             the board says who it is
      EPD-Device-Version: <version>     and what it runs

      200 image/png
      EPD-Next-Display-Refresh-Seconds: <seconds until the next scheduled wake>
      EPD-Next-URL: http://host/<the page to fetch at that wake>
      EPD-Server-Version: <version>               this server, on every response
      EPD-Server-Epoch-Seconds: <UTC seconds>     its clock, on every response
      EPD-Server-Firmware-Version: <version>      on any response, when an update applies
      EPD-Server-Firmware-URL: http://host/firmware.bin
      EPD-Next-Sensor-Poll-Seconds: <seconds>     when a board that posts readings
                                                  should post next, on every response
                                                  when the project sets sensor_poll

    GET /firmware.bin[?product=<name>&version=<version>]
      200 application/octet-stream, Content-Length, x-MD5
      304 when the request's x-ESP32-version is the version held
      404 when the server holds no such image

    POST /<name>        a project's ingest route: a JSON object, or an array
                        of them, in; 204 out, or 200 with the handler's JSON;
                        409 when version_gate is on and the board's version
                        cannot work with the server's
    GET /<name>?k=v     a project's query route: JSON out, 404 when there
                        is no answer

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
from urllib.parse import urlencode

from flask import Flask, abort, jsonify, make_response, request, send_file
from werkzeug.serving import WSGIRequestHandler, make_server

from .compat import compatible, version_order
from .config import FirmwareSettings, MqttSettings
from ._version import __version__
from .headers import Wire
from .firmware import (FirmwareImage, FirmwareStore, ReleaseWatcher, client_from_headers,
                       update_applies)
from .logs import LogStore
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


# What a page asked for before the first render has written it tells the
# board to wait: about as long as rendering every page takes.
FIRST_RENDER_RETRY_AFTER_S = 30


CONNECTION_TIMEOUT_S = 30


class ServerThread(threading.Thread):
    """Werkzeug's threaded dev server on a daemon thread, with a clean shutdown."""

    def __init__(self, app: Flask, host: str, port: int,
                 timeout_s: float = CONNECTION_TIMEOUT_S):
        super().__init__(daemon=True, name="epd-http")
        handler = type("TimedRequestHandler", (WSGIRequestHandler,), {"timeout": timeout_s})
        self.server = make_server(host, port, app, threaded=True, request_handler=handler)
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
        mqtt: if given and ``enabled``, relay every board's log topic into
            the ``client`` logger while running.
        client_logs: where the relayed lines are kept, if anywhere.
        mqtt_client_id: the id this server connects to the broker with.
        ingest: routes that accept documents by POST, as ``{name: handler}``.
            ``POST /<name>`` takes one JSON object or an array of them and
            calls ``handler(docs)`` once with the list, so a batch can be
            written in one transaction. What the handler returns is sent as
            JSON with a 200, and None is a 204; a ``ValueError`` is a 400.
        queries: routes that answer a GET with JSON, as ``{name: handler}``.
            ``GET /<name>`` calls ``handler(args)`` with the query string as
            a dict and sends what it returns; None is a 404 and a
            ``ValueError`` a 400. A name may have both kinds of route.
        firmware: if given and ``enabled``, offer an image from its directory
            to the boards it is for, on any response to one, and serve it at
            ``/firmware.bin``. With ``version_gate`` the offer is the newest
            image that can work with ``server_version``, older than the
            board's own or newer; without it, the newest file.
        header_prefix: the product's name, which every header on the wire
            starts with. See :mod:`epd_server.headers`.
        server_version: what to report as this server's version. Defaults to
            the version of this package, which is right until a project has
            one of its own.
        version_gate: refuse an ingest post, with 409, from a board whose
            version cannot work with ``server_version``, and offer each board
            the image its server calls for. Only for a project whose boards
            and server take their versions from the same tags; see
            :mod:`epd_server.compat`.
        on_refused: called with the board's name and version each time the
            version gate refuses one, so the project can say so on its pages.
        sensor_poll: the seconds until a board that posts readings should post
            next, given the epoch now. Sent on every response when given, so
            a board learns it from whatever request it last made.
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
        client_logs: LogStore | None = None,
        ingest: Mapping[str, Callable[[list[dict]], dict | None]] | None = None,
        queries: Mapping[str, Callable[[dict], object]] | None = None,
        firmware: FirmwareSettings | None = None,
        header_prefix: str = "EPD",
        server_version: str | None = None,
        version_gate: bool = False,
        sensor_poll: Callable[[float], int] | None = None,
        on_refused: Callable[[str, str], None] | None = None,
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
        self.client_logs = client_logs
        self.ingest = dict(ingest or {})
        self.queries = dict(queries or {})
        self.firmware = firmware
        self.wire = Wire(header_prefix)
        self.server_version = server_version or __version__
        self.version_gate = version_gate
        self.sensor_poll = sensor_poll
        self.on_refused = on_refused
        self.firmware_stores = ({p: FirmwareStore(firmware.dir_for(p)) for p in firmware.names()}
                                if firmware and firmware.enabled else {})
        # The default product's: what the release watcher fills and / reports.
        self.firmware_store = self.firmware_stores.get(firmware.product) if firmware else None
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
        clash = sorted(set(self.queries) & served)
        if clash:
            raise ValueError(f"query routes {clash} collide with page filenames")

        # Serialises regenerations; a page's PNG is replaced atomically, so
        # readers never wait on it.
        self.regen_lock = threading.Lock()
        # Set while run() renders every page for the first time, on its own
        # thread, with the server already answering.
        self.first_render_pending = threading.Event()
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

        app.before_request(self._log_client)
        app.after_request(self._add_server_headers)

        @app.route("/")
        def index():
            seconds, path = self.next_wake()
            image = self._offer_image(self.firmware.product) if self.firmware else None
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
        for name, handler in self.queries.items():
            app.add_url_rule(
                "/" + name,
                endpoint=f"query_{name}",
                view_func=self._make_query(name, handler),
                methods=["GET"],
            )
        return app

    def _make_query(self, name: str, handler: Callable[[dict], object]):
        def answer():
            try:
                result = handler(request.args.to_dict())
            except ValueError as exc:
                abort(400, str(exc))
            if result is None:
                abort(404)
            return jsonify(result)
        answer.__name__ = f"query_{name}"
        return answer

    def _make_ingest(self, name: str, handler: Callable[[list[dict]], dict | None]):
        def accept():
            refusal = self._version_refusal()
            if refusal is not None:
                return refusal
            body = request.get_json(silent=True)
            docs = [body] if isinstance(body, dict) else body
            if not isinstance(docs, list) or not docs or not all(isinstance(d, dict) for d in docs):
                abort(400, "expected a JSON object or a non-empty array of objects")
            try:
                result = handler(docs)
            except ValueError as exc:
                abort(400, str(exc))
            if result is None:
                return "", 204
            return jsonify(result)
        accept.__name__ = f"ingest_{name}"
        return accept

    def _version_refusal(self):
        """A 409 for a board whose version cannot work with this server's.

        A board that states no version, or one that cannot be read, is let
        through: it cannot be judged, and refusing it would silently stop the
        readings of every development build. The body names both versions so
        the board can log them.
        """
        if not self.version_gate:
            return None
        device = request.headers.get(self.wire.device)
        version = request.headers.get(self.wire.device_version)
        if compatible(version, self.server_version) is not False:
            return None
        log.warning("refused %s from %s %s: this server is %s", request.path,
                    device or "an unnamed client", version, self.server_version)
        if self.on_refused is not None:
            self.on_refused(device or "", version or "")
        return jsonify(error="version", device=version, server=self.server_version), 409

    def _offer_image(self, product: str) -> FirmwareImage | None:
        """The image a board of ``product`` should run, before asking whether
        it runs it already."""
        store = self.firmware_stores.get(product)
        if store is None:
            return None
        return store.newest_compatible(self.server_version) if self.version_gate else store.current()

    def _firmware_url(self, image: FirmwareImage, product: str) -> str:
        url = request.host_url.rstrip("/") + "/firmware.bin"
        if self.firmware is not None and self.firmware.products:
            url += "?" + urlencode({"product": product, "version": image.version})
        return url

    def _serve_firmware(self):
        """The image itself. The board asks for this after a response offered it."""
        assert self.firmware is not None   # the route exists only when it does
        product = request.args.get("product") or self.firmware.product
        version = request.args.get("version")
        store = self.firmware_stores.get(product)
        if store is None:
            abort(404)
        image = store.image(version) if version else self._offer_image(product)
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
        if not self.firmware_stores or request.endpoint == "firmware":
            return
        firmware = self.firmware
        assert firmware is not None   # the stores exist only when it does
        client = client_from_headers(request.headers.get(self.wire.device),
                                     request.headers.get(self.wire.device_version))
        image = self._offer_image(client.name) if client is not None else None
        if not update_applies(client, image, firmware):
            return
        assert image is not None and client is not None   # update_applies said so
        url = self._firmware_url(image, client.name)
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

    def _make_view(self, page: Page):
        def serve():
            return self._serve(page)
        serve.__name__ = f"serve_{page.name}"
        return serve

    def _serve(self, page: Page):
        path = page.png_path
        if not os.path.exists(path):
            if self.first_render_pending.is_set():
                rsp = make_response("The pages are still being rendered after a start.\n", 503)
                rsp.headers["Retry-After"] = str(FIRST_RENDER_RETRY_AFTER_S)
                return rsp
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
        rsp.headers[self.wire.next_refresh] = str(seconds)
        rsp.headers[self.wire.next_url] = next_url
        return rsp

    def _log_client(self) -> None:
        """Log the identity the board stated, when it stated one."""
        name = request.headers.get(self.wire.device)
        version = request.headers.get(self.wire.device_version)
        if name or version:
            log.info("%s %s asked for %s", name or "an unnamed client",
                     version or "of no stated version", request.path)

    def _add_server_headers(self, rsp):
        """Stamp every response with who is serving it and when.

        The clock goes out on every response so a board without one of its
        own can keep time from the server it already has to reach.
        """
        now = time.time()
        rsp.headers[self.wire.server_version] = self.server_version
        rsp.headers[self.wire.server_epoch] = str(int(now))
        if self.sensor_poll is not None:
            rsp.headers[self.wire.next_sensor_poll] = str(int(self.sensor_poll(now)))
        self._firmware_headers(rsp)
        return rsp

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def run(self, once: bool = False, install_signal_handlers: bool = True) -> None:
        """Serve at once, render every page on a thread of its own, and follow
        the schedule until stopped.

        ``once=True`` renders everything and returns without starting the
        HTTP server, the log relay, or the loop — handy while iterating on
        pages.
        """
        if once:
            self.regenerate()
            log.info("once: images generated, not starting the server")
            return
        self.first_render_pending.set()

        if self.mqtt is not None and self.mqtt.enabled:
            self.mqtt_client = client_log_subscriber(
                self.mqtt.host, self.mqtt.port, self.mqtt.prefix, client_id=self.mqtt_client_id,
                on_line=self.client_logs.add if self.client_logs is not None else None,
            )

        source = self.firmware.source if self.firmware else None
        if self.firmware_store is not None and source is not None:
            self.release_watcher = ReleaseWatcher(self.firmware_store, source)
            log.info("Watching %s for releases every %ds", source.github,
                     source.poll_seconds)
            threading.Thread(target=self.release_watcher.run, name="epd-releases",
                             daemon=True).start()

        self.http = ServerThread(self.app, self.host, self.port)
        self.http.start()
        threading.Thread(target=self._first_render, name="epd-first-render", daemon=True).start()

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

    def _first_render(self) -> None:
        """Render every page, once, while the server already answers. A
        failure leaves each page to its scheduled render."""
        try:
            self.regenerate()
        except Exception:  # noqa: BLE001 - the server keeps serving what it has
            log.exception("First render failed; each page renders at its scheduled time")
        finally:
            self.first_render_pending.clear()

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
