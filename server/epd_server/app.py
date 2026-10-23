"""The server: serve page PNGs on a schedule, regenerating each one just
before its client wake time.

A project builds its pages and a :class:`~epd_server.source.DataSource`,
hands them to :class:`DisplayServer` with the validated settings, and calls
:meth:`DisplayServer.run`. Everything else — HTTP routes, an optional HTTPS
port for a browser, the schedule and identity headers, the regeneration
loop, the client log relay, signal handling — lives here, except three parts
that each have a module of their own: the firmware offered to the boards
(:mod:`epd_server.offers`), the install routes
(:mod:`epd_server.install_routes`), and the board keys on the wire
(:mod:`epd_server.key_routes`).

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
      EPD-Server-Timezone: <POSIX TZ string>      its zone, on every response, when
                                                  the zone has an IANA name
      EPD-Server-Firmware-Version: <version>      on any response, when an update applies
      EPD-Server-Firmware-URL: http://host/firmware.bin
      EPD-Next-Sensor-Poll-Seconds: <seconds>     when the board should post or sync
                                                  next, on every response when the
                                                  project's sensor_poll gives one for it

    GET /firmware.bin[?product=<name>&version=<version>]
      200 application/octet-stream, Content-Length, x-MD5, Content-Digest;
          signed for a board whose key the server holds (epd_server.board_keys)
      304 when the request's x-ESP32-version is the version held
      404 when the server holds no such image

    GET /firmware.merged.bin[?product=<name>]
      200 application/octet-stream, Content-Length, x-MD5, Content-Digest: the
          merged image of the version offered over the air, for a USB flash
          from address 0
      404 when the server holds no such image

    GET /network.bin[?product=<name>]
      200 application/octet-stream: the board's settings store with the
          network settings, for a USB flash at 0x9000
      404 when the server has no such product
      409 when a key it needs is not set; the body names them

    GET /install        the install page, for a person with a board on USB
    GET /install/<name> its two scripts
    GET /install-firmware.sh  the same install from a terminal, with this
                        server's address filled in; text/plain, no-store
    (the three /install routes exist only with install_boards; see
    epd_server.install_routes)

    POST /<name>        a project's ingest route: a JSON object, or an array
                        of them, in; 204 out, or 200 with the handler's JSON;
                        409 when version_gate is on and the board's version
                        cannot work with the server's; 401 with EPD-Key when
                        signatures are required and the post has no good one
    GET /<name>?k=v     a project's query route: JSON out, 404 when there
                        is no answer; signed when it is in signed_queries
    POST /pair          a board's half of its key exchange in, the server's
                        out (only while signatures are required)

The server is the single source of truth for *when* the client wakes and
*what* it shows. The client does no timezone maths and holds no schedule.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

from flask import Flask, abort, jsonify, make_response, request
from werkzeug.serving import WSGIRequestHandler, make_server

from ._version import __version__
from .board_keys import BoardKeys
from .certificate import certificate_names, ensure_certificate
from .compat import compatible
from .config import FirmwareSettings, MqttSettings, NetworkSettings
from .firmware import ReleaseWatcher
from .headers import Wire
from .install import INSTALLER, InstallBoard
from .install_routes import InstallRoutes
from .key_routes import KeyRoutes
from .logs import LogStore
from .mqtt import client_log_subscriber
from .offers import FirmwareOffers
from .page import Page
from .pipeline import regenerate as _regenerate
from .posix_tz import posix_tz
from .responses import download
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
    """Werkzeug's threaded dev server on a daemon thread, with a clean shutdown.
    With ``ssl_context``, a certificate and key path, it serves HTTPS."""

    def __init__(self, app: Flask, host: str, port: int,
                 timeout_s: float = CONNECTION_TIMEOUT_S,
                 ssl_context: tuple[str, str] | None = None):
        self.scheme = "https" if ssl_context else "http"
        super().__init__(daemon=True, name=f"epd-{self.scheme}")
        handler = type("TimedRequestHandler", (WSGIRequestHandler,), {"timeout": timeout_s})
        self.server = make_server(host, port, app, threaded=True, request_handler=handler,
                                  ssl_context=ssl_context)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        log.info("Starting %s server on %s:%d", self.scheme, *self.server.server_address[:2])
        self.server.serve_forever()

    def shutdown(self):
        log.info("Stopping %s server", self.scheme)
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
        tz: the timezone the schedule times are in. When it has an IANA name,
            every response carries it as a POSIX TZ string.
        regen_lead_seconds: regenerate this long before each wake.
        host, port: where to listen.
        https_port: where to serve the same routes over HTTPS as well, with a
            self-signed certificate kept in ``certificate_dir``; 0 for none.
            The install page needs HTTPS, unless a reverse proxy gives it.
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
            ``/firmware.bin`` and its merged image at ``/firmware.merged.bin``.
            With ``version_gate`` the offer is the newest image that can work
            with ``server_version``, older than the board's own or newer;
            without it, the newest file.
        network: if given with ``firmware``, serve each product's network
            settings at ``/network.bin``, for a USB flash. The install routes
            read it at each request, so a project can replace
            ``server.network`` while the server runs.
        install_boards: the boards the install page at ``/install`` offers.
            It needs ``firmware`` and ``network``.
        settings_url: where the install page sends a person to change a
            setting, relative to this server's root.
        install_url: the project's own install page, relative to this
            server's root, when that page holds the network settings. The
            page and install-firmware.sh then send a person there to set them,
            and to ``settings_url`` only for the HTTPS port.
        login_url: the project's sign-in form, relative to this server's
            root, when the project puts a sign-in in front of
            ``/network.bin``. On a 401 there, install-firmware.sh asks for
            the password, posts it to this form as the field ``password``,
            and sends the cookie it gets back. A 401 from the form is a wrong
            password; a 429 is too many tries, with Retry-After.
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
        sensor_poll: the seconds until a board should post or sync next,
            given the epoch now and the name the board states, None when it
            states none; None back sends no header. Sent on every response
            it answers, so a board learns it from whatever request it last
            made.
        board_keys: the boards' keys (:mod:`epd_server.board_keys`). With
            them, the image and each query in ``signed_queries`` are signed
            for a board whose key the server holds: the one it names in
            ``<prefix>-Key-Id``, else its approved one.
        require_signatures: with ``board_keys``, offer ``POST /pair``, and
            refuse every ingest post without a good signature from an
            approved key, with a 401 whose ``<prefix>-Key`` header says what
            the board should do.
        signed_queries: the query routes whose answers change a board, which
            it takes only signed once it has a key.
        choose_page: picks a wake's page from the data. Just before the
            server makes the page for a wake, it calls this with the
            scheduled page's filename and the wake, and makes the filename it
            returns. The display's fetch of the scheduled page then gets the
            page made, until the next wake's page is made; ``EPD-Next-URL``
            still names the scheduled page. A failure, or a filename this
            server does not serve, makes the scheduled page.
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
        https_port: int = 0,
        certificate_dir: str | None = None,
        mqtt: MqttSettings | None = None,
        mqtt_client_id: str = "epd-server",
        client_logs: LogStore | None = None,
        ingest: Mapping[str, Callable[[list[dict]], dict | None]] | None = None,
        queries: Mapping[str, Callable[[dict], object]] | None = None,
        firmware: FirmwareSettings | None = None,
        network: NetworkSettings | None = None,
        install_boards: Iterable[InstallBoard] = (),
        settings_url: str | None = None,
        install_url: str | None = None,
        login_url: str | None = None,
        header_prefix: str = "EPD",
        server_version: str | None = None,
        version_gate: bool = False,
        sensor_poll: Callable[[float, str | None], int | None] | None = None,
        on_refused: Callable[[str, str], None] | None = None,
        board_keys: BoardKeys | None = None,
        require_signatures: bool = False,
        signed_queries: Iterable[str] = (),
        choose_page: Callable[[str, datetime], str] | None = None,
    ):
        self.pages = list(pages)
        self.source = source
        self.tz = tz
        self.posix_tz = posix_tz(tz)
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
        self.https_port = https_port
        self.certificate_dir = certificate_dir
        self.mqtt = mqtt
        self.mqtt_client_id = mqtt_client_id
        self.client_logs = client_logs
        self.ingest = dict(ingest or {})
        self.queries = dict(queries or {})
        self.firmware = firmware
        self.network = network
        self.install_boards = list(install_boards)
        self.settings_url = settings_url
        self.install_url = install_url
        self.login_url = login_url
        self.wire = Wire(header_prefix)
        self.server_version = server_version or __version__
        self.version_gate = version_gate
        self.sensor_poll = sensor_poll
        self.on_refused = on_refused
        self.board_keys = board_keys
        self.require_signatures = require_signatures
        self.signed_queries = tuple(signed_queries)
        self.choose_page = choose_page
        self.made_for: dict[str, str] = {}
        self.offers = FirmwareOffers(firmware, version_gate=version_gate,
                                     server_version=self.server_version, wire=self.wire)
        self.firmware_stores = self.offers.stores
        self.firmware_store = self.offers.store
        self.release_watcher: ReleaseWatcher | None = None

        if not self.pages:
            raise ValueError("DisplayServer needs at least one page")
        if https_port and not certificate_dir:
            raise ValueError("DisplayServer needs a certificate_dir for its https_port")
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
        clash = sorted((set(self.ingest) | set(self.queries)) & {"install", INSTALLER})
        if clash:
            raise ValueError(f"routes {clash} collide with the install page")
        if require_signatures and board_keys is None:
            raise ValueError("require_signatures needs board_keys")
        if board_keys is not None and "pair" in set(self.ingest) | set(self.queries):
            raise ValueError("a route named pair collides with the boards' pairing")
        unknown = sorted(set(self.signed_queries) - set(self.queries))
        if unknown:
            raise ValueError(f"signed_queries {unknown} are not queries")
        if self.install_boards:
            if firmware is None or network is None:
                raise ValueError("the install page needs firmware and network settings")
            unknown = sorted({b.product for b in self.install_boards} - set(firmware.names()))
            if unknown:
                raise ValueError(f"install boards {unknown} are not in client.firmware")

        self.keys = (KeyRoutes(board_keys, require_signatures=require_signatures,
                               signed_queries=self.signed_queries, wire=self.wire)
                     if board_keys is not None else None)
        self.installs = InstallRoutes(
            firmware=firmware, network=lambda: self.network, mqtt=mqtt, offers=self.offers,
            boards=self.install_boards, https_port=https_port,
            first_page=self.pages[0].png_filename, settings_url=settings_url,
            install_url=install_url, login_url=login_url)

        # Serialises regenerations; a page's PNG is replaced atomically, so
        # readers never wait on it.
        self.regen_lock = threading.Lock()
        # Set while run() renders every page for the first time, on its own
        # thread, with the server already answering.
        self.first_render_pending = threading.Event()
        self.shutdown_event = threading.Event()
        self.http: ServerThread | None = None
        self.https: ServerThread | None = None
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
            image = self.offers.offer(self.firmware.product) if self.firmware else None
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

        self.offers.register(app)
        self.installs.register(app)
        if self.keys is not None:
            self.keys.register(app)

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

    def install_config(self, root: str = "", network_here: bool = False) -> dict:
        """What the install page's script needs to know, for a page that is
        ``root`` away from this server's root: "" for ``/install``, "../" for a
        page one directory down, as a project draws it in its own layout.
        ``network_here`` says the page holds the network settings itself."""
        return self.installs.config(root, network_here)

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
            refusal = self._version_refusal() or (self.keys.refusal() if self.keys else None)
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

    def _make_view(self, page: Page):
        def serve():
            return self._serve(page)
        serve.__name__ = f"serve_{page.name}"
        return serve

    def _serve(self, page: Page):
        made = self.made_for.get(page.png_filename)
        page = next((p for p in self.pages if p.png_filename == made), page)
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

        rsp = download(data, page.png_filename, mimetype="image/png")
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
        """Stamp every response with who is serving it, and when and where.

        The clock and the zone go out on every response so a board without
        one of its own can keep local time from the server it already has to
        reach.
        """
        now = time.time()
        rsp.headers[self.wire.server_version] = self.server_version
        rsp.headers[self.wire.server_epoch] = str(int(now))
        if self.posix_tz:
            rsp.headers[self.wire.server_timezone] = self.posix_tz
        if self.sensor_poll is not None:
            name = (request.headers.get(self.wire.device) or "").strip() or None
            seconds = self.sensor_poll(now, name)
            if seconds is not None:
                rsp.headers[self.wire.next_sensor_poll] = str(int(seconds))
        self.offers.add_headers(rsp)
        if self.keys is not None:
            self.keys.sign(rsp)
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
        if self.https_port:
            self._start_https()
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

    def _start_https(self) -> None:
        """Serve HTTPS too. A failure leaves the server on plain HTTP alone,
        since the boards need only that."""
        assert self.certificate_dir is not None   # checked in __init__
        names = certificate_names(self.network.server_url if self.network else "")
        try:
            paths = ensure_certificate(self.certificate_dir, names)
            self.https = ServerThread(self.app, self.host, self.https_port, ssl_context=paths)
        except (OSError, ValueError) as exc:
            log.error("No HTTPS on port %d: %s", self.https_port, exc)
            return
        self.https.start()

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
            chosen = self._choose(path, wake_dt)
            self.made_for = {}
            try:
                self.regenerate(only=chosen, force_refresh=True)
            except Exception:  # noqa: BLE001 - keep serving; retry at the next slot
                log.exception("Scheduled regeneration failed; will retry at next regen time")
            else:
                if chosen != path:
                    self.made_for = {path: chosen}

    def _choose(self, path: str, wake_dt: datetime) -> str:
        """The page to make for the wake at ``wake_dt``: ``choose_page``'s
        answer when it names a page this server serves, else ``path``."""
        if self.choose_page is None:
            return path
        try:
            chosen = self.choose_page(path, wake_dt)
        except Exception:  # noqa: BLE001 - the scheduled page is always a good answer
            log.exception("choose_page failed; making %s", path)
            return path
        if chosen not in {p.png_filename for p in self.pages}:
            log.error("choose_page named %r, which this server does not serve; making %s",
                      chosen, path)
            return path
        if chosen != path:
            log.info("Making %s in place of %s", chosen, path)
        return chosen

    def _shutdown(self) -> None:
        if self.release_watcher is not None:
            self.release_watcher.stop()
            self.release_watcher = None
        if self.http is not None:
            self.http.shutdown()
            self.http = None
        if self.https is not None:
            self.https.shutdown()
            self.https = None
        if self.mqtt_client is not None:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.mqtt_client = None
        log.info("Exited")
