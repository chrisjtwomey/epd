"""DisplayServer: routes, headers, schedule checks, regeneration, lifecycle."""
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from epd_server.app import (FIRST_RENDER_RETRY_AFTER_S, DisplayServer, ServerThread,
                            align_process_timezone)
from epd_server.config import MqttSettings
from epd_server.logs import LogStore
from epd_server.source import StaticSource

from .test_pipeline import RecordingPage

UTC = ZoneInfo("UTC")
PNG = b"\x89PNG\r\n\x1a\n"


def make(tmp_path, schedule=None, pages=None, **kw):
    pages = pages or [RecordingPage("today", ("x",)), RecordingPage("hourly", ("x",))]
    for p in pages:
        p.png_dir = str(tmp_path)
        p.html_dir = str(tmp_path / "html")
    return DisplayServer(
        pages=pages,
        source=StaticSource(x=1),
        schedule=schedule if schedule is not None else [("09:00:00", "today.png"), ("15:00:00", "hourly.png")],
        tz=UTC,
        **kw,
    )


@pytest.fixture
def server(tmp_path):
    (tmp_path / "today.png").write_bytes(PNG)
    (tmp_path / "hourly.png").write_bytes(PNG)
    return make(tmp_path)


@pytest.fixture
def client(server):
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


# ---------- construction checks ----------

def test_schedule_must_name_pages_the_server_produces(tmp_path):
    with pytest.raises(ValueError, match=r"names \['nope.png'\], but the pages only produce \['hourly.png', 'today.png'\]"):
        make(tmp_path, schedule=[("09:00:00", "nope.png")])


def test_needs_pages_and_a_schedule(tmp_path):
    with pytest.raises(ValueError, match="at least one page"):
        DisplayServer(pages=[], source=StaticSource(), schedule=[("09:00:00", "a.png")], tz=UTC)
    with pytest.raises(ValueError, match="non-empty schedule"):
        make(tmp_path, schedule=[])


# ---------- routes ----------

def test_each_page_is_served_with_next_wake_headers(client):
    for name in ("today.png", "hourly.png"):
        rsp = client.get("/" + name)
        assert rsp.status_code == 200
        assert rsp.mimetype == "image/png"
        assert rsp.data == PNG
        assert int(rsp.headers["EPD-Next-Display-Refresh-Seconds"]) >= 0
        assert rsp.headers["EPD-Next-URL"].startswith("http://localhost/")
        assert rsp.headers["EPD-Next-URL"].endswith(".png")


def test_missing_png_is_404(tmp_path):
    srv = make(tmp_path)  # no files written
    srv.app.config["TESTING"] = True
    with srv.app.test_client() as c:
        assert c.get("/today.png").status_code == 404


def test_a_page_not_rendered_since_the_start_is_a_503_that_says_when_to_retry(tmp_path):
    srv = make(tmp_path)  # no files written
    srv.first_render_pending.set()
    with srv.app.test_client() as c:
        rsp = c.get("/today.png")
        assert rsp.status_code == 503
        assert rsp.headers["Retry-After"] == str(FIRST_RENDER_RETRY_AFTER_S)
        srv.first_render_pending.clear()
        assert c.get("/today.png").status_code == 404


def test_unknown_route_is_404(client):
    assert client.get("/nope.png").status_code == 404


def test_index_lists_pages_schedule_and_next_wake(client):
    body = client.get("/").get_json()
    assert body["pages"] == ["today.png", "hourly.png"]
    assert body["schedule"]["type"] == "times"
    assert body["schedule"]["times"] == [{"time": "09:00:00", "pool": "today.png"},
                                         {"time": "15:00:00", "pool": "hourly.png"}]
    assert body["schedule"]["pools"] == {"today.png": ["today.png"], "hourly.png": ["hourly.png"]}
    assert body["next_wake_seconds"] >= 0
    assert body["next_page"] in ("today.png", "hourly.png")


# ---------- next_wake ----------

def test_next_wake_reports_seconds_and_page(server):
    now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC)
    assert server.next_wake(now=now) == (5 * 3600, "hourly.png")
    now = datetime(2026, 7, 1, 23, 0, 0, tzinfo=UTC)
    assert server.next_wake(now=now) == (10 * 3600, "today.png")


# ---------- regenerate ----------

def test_regenerate_delegates_to_pipeline_under_the_lock(server):
    rendered = server.regenerate(only="hourly.png", force_refresh=True)
    assert [p.name for p in rendered] == ["hourly"]
    assert server.pages[1].saves == 1 and server.pages[0].saves == 0
    assert not server.regen_lock.locked()


def test_regenerate_all(server):
    assert [p.name for p in server.regenerate()] == ["today", "hourly"]


# ---------- run / loop ----------

def test_run_once_regenerates_and_does_not_start_http(server):
    server.run(once=True)
    assert all(p.saves == 1 for p in server.pages)
    assert server.http is None and server.mqtt_client is None


class OneTickEvent(threading.Event):
    """A threading.Event stand-in that lets _loop() run exactly one iteration.

    is_set() is False on the first check (enter the loop) and True after
    that (leave it). wait() returns immediately and never reports a shutdown,
    so the iteration reaches regenerate().
    """

    def __init__(self):
        self.waits = []
        self.checks = 0

    def is_set(self):
        self.checks += 1
        return self.checks > 1

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return False

    def set(self):
        self.checks = 99


def test_loop_regenerates_the_scheduled_page_with_force_refresh(server, monkeypatch):
    calls = []
    monkeypatch.setattr(server, "regenerate",
                        lambda only=None, force_refresh=False: calls.append((only, force_refresh)))
    server.shutdown_event = OneTickEvent()
    server._loop()
    assert len(calls) == 1
    only, force = calls[0]
    assert only in ("today.png", "hourly.png") and force is True
    assert server.shutdown_event.waits and server.shutdown_event.waits[0] >= 0


def test_loop_survives_a_failed_regeneration(server, monkeypatch, caplog):
    def boom(only=None, force_refresh=False):
        raise RuntimeError("weather api down")
    monkeypatch.setattr(server, "regenerate", boom)
    server.shutdown_event = OneTickEvent()
    server._loop()   # must not raise
    assert "Scheduled regeneration failed" in caplog.text


def test_stop_sets_the_shutdown_event(server):
    assert not server.shutdown_event.is_set()
    server.stop()
    assert server.shutdown_event.is_set()


def test_run_starts_and_stops_http_on_a_free_port(tmp_path):
    (tmp_path / "today.png").write_bytes(PNG)
    srv = make(tmp_path, port=0)      # 0 = OS picks a free port
    srv.shutdown_event = OneTickEvent()
    srv.run(install_signal_handlers=False)
    assert srv.http is None            # shut down cleanly


def test_run_answers_before_the_first_render_is_done(tmp_path, monkeypatch):
    srv = make(tmp_path, port=0)
    rendering, finish = threading.Event(), threading.Event()

    def slow(only=None, force_refresh=False):
        rendering.set()
        finish.wait(5)
        return []
    monkeypatch.setattr(srv, "regenerate", slow)
    runner = threading.Thread(target=srv.run, kwargs={"install_signal_handlers": False},
                              daemon=True)
    runner.start()
    try:
        assert rendering.wait(5)
        port = srv.http.server.server_port
        with pytest.raises(urllib.error.HTTPError) as answer:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/today.png", timeout=5)
        assert answer.value.code == 503
    finally:
        finish.set()
        srv.stop()
        runner.join(5)
    assert not srv.first_render_pending.is_set()


@pytest.fixture
def live(server):
    """The server's app on a free port, with a short connection timeout."""
    http = ServerThread(server.app, "127.0.0.1", 0, timeout_s=0.5)
    http.start()
    yield http.server.server_port
    http.shutdown()


def test_an_idle_connection_does_not_hold_up_other_requests(live):
    idle = socket.create_connection(("127.0.0.1", live))   # connects, sends nothing
    try:
        started = time.monotonic()
        with urllib.request.urlopen(f"http://127.0.0.1:{live}/today.png", timeout=5) as rsp:
            assert rsp.status == 200
        assert time.monotonic() - started < 2
    finally:
        idle.close()


def test_an_idle_connection_is_closed_after_the_timeout(live):
    idle = socket.create_connection(("127.0.0.1", live))
    idle.settimeout(5)
    try:
        assert idle.recv(1) == b""          # the server hung up
    finally:
        idle.close()


def test_a_failed_first_render_leaves_the_server_serving(server, monkeypatch, caplog):
    def boom(only=None, force_refresh=False):
        raise RuntimeError("weather api down")
    monkeypatch.setattr(server, "regenerate", boom)
    server.first_render_pending.set()
    server._first_render()   # must not raise
    assert not server.first_render_pending.is_set()
    assert "First render failed" in caplog.text


def test_mqtt_relay_is_only_started_when_enabled(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr("epd_server.app.client_log_subscriber",
                        lambda *a, **k: started.append((a, k)) or None)
    srv = make(tmp_path, port=0, mqtt=MqttSettings(False, "h", 1883, "t"))
    srv.shutdown_event = OneTickEvent()
    srv.run(install_signal_handlers=False)
    assert started == []

    srv = make(tmp_path, port=0, mqtt=MqttSettings(True, "h", 1883, "t"), mqtt_client_id="me")
    srv.shutdown_event = OneTickEvent()
    srv.run(install_signal_handlers=False)
    assert started == [(("h", 1883, "t"), {"client_id": "me", "on_line": None})]


def test_the_relay_keeps_each_line_when_given_a_store(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr("epd_server.app.client_log_subscriber",
                        lambda *a, **k: started.append(k) or None)
    logs = LogStore(":memory:")
    srv = make(tmp_path, port=0, mqtt=MqttSettings(True, "h", 1883, "t"), client_logs=logs)
    srv.shutdown_event = OneTickEvent()
    srv.run(install_signal_handlers=False)
    started[0]["on_line"]("canary-dock", "INFO - hello")
    assert [line["text"] for line in logs.lines()] == ["INFO - hello"]


# ---------- align_process_timezone ----------

def test_align_process_timezone_sets_tz_for_iana_zones(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    align_process_timezone(ZoneInfo("Europe/Dublin"))
    assert os.environ["TZ"] == "Europe/Dublin"
    if hasattr(time, "tzset"):
        assert time.strftime("%Z", time.localtime(1751364000)) in ("IST", "GMT")  # 2025-07-01
    align_process_timezone(UTC)   # restore for later tests


def test_align_process_timezone_ignores_zones_without_a_key(monkeypatch):
    from datetime import timedelta, timezone
    monkeypatch.setenv("TZ", "UTC")
    align_process_timezone(timezone(timedelta(hours=2)))
    assert os.environ["TZ"] == "UTC"


# ---------- ingest ----------

def test_ingest_route_parses_json_and_calls_the_handler(tmp_path):
    seen = []
    server = make(tmp_path, ingest={"readings": seen.extend})
    client = server._build_app().test_client()

    rsp = client.post("/readings", json={"ts": 1, "co2_ppm": 640})

    assert rsp.status_code == 204 and rsp.data == b""
    assert seen == [{"ts": 1, "co2_ppm": 640}]


@pytest.mark.parametrize("data, content_type", [
    (b"not json", "application/json"),
    (b"[1, 2]", "application/json"),
    (b'[{"ts": 1}, 2]', "application/json"),
    (b"[]", "application/json"),
    (b"7", "application/json"),
    (b'{"ts": 1}', "text/plain"),
])
def test_ingest_rejects_anything_but_an_object_or_an_array_of_them(tmp_path, data, content_type):
    seen = []
    server = make(tmp_path, ingest={"readings": seen.extend})
    client = server._build_app().test_client()

    rsp = client.post("/readings", data=data, content_type=content_type)

    assert rsp.status_code == 400 and seen == []


def test_ingest_hands_an_array_to_the_handler_in_one_call(tmp_path):
    calls = []
    server = make(tmp_path, ingest={"readings": calls.append})
    client = server._build_app().test_client()

    rsp = client.post("/readings", json=[{"ts": 1}, {"ts": 2}])

    assert rsp.status_code == 204
    assert calls == [[{"ts": 1}, {"ts": 2}]]


def test_ingest_sends_what_the_handler_returns_as_json(tmp_path):
    server = make(tmp_path, ingest={"readings": lambda docs: {"new": len(docs)}})
    client = server._build_app().test_client()

    rsp = client.post("/readings", json=[{"ts": 1}, {"ts": 2}])

    assert rsp.status_code == 200 and rsp.get_json() == {"new": 2}


def test_a_store_as_the_handler_takes_a_repeat_once(tmp_path):
    from epd_server import ReadingsStore
    store = ReadingsStore(":memory:")
    client = make(tmp_path, ingest={"readings": store.add_many})._build_app().test_client()

    assert client.post("/readings", json={"ts": 1, "device": "a"}).get_json() == [True]
    rsp = client.post("/readings", json=[{"ts": 1, "device": "a"}, {"ts": 2, "device": "a"}])

    assert rsp.status_code == 200 and rsp.get_json() == [False, True]
    assert store.count() == 2


def test_ingest_handler_value_error_is_a_400_with_its_message(tmp_path):
    def reject(docs):
        raise ValueError("ts is required")
    server = make(tmp_path, ingest={"readings": reject})
    client = server._build_app().test_client()

    rsp = client.post("/readings", json={})

    assert rsp.status_code == 400 and b"ts is required" in rsp.data


def test_ingest_route_is_post_only_and_cannot_shadow_a_page(tmp_path):
    server = make(tmp_path, ingest={"readings": lambda doc: None})
    assert server._build_app().test_client().get("/readings").status_code == 405
    with pytest.raises(ValueError, match="collide"):
        make(tmp_path, ingest={"today.png": lambda doc: None})


# ---------- queries ----------

def test_query_route_answers_a_get_with_the_handlers_json(tmp_path):
    asked = []

    def answer(args):
        asked.append(args)
        return {"bme688": {"state": "AAEC"}}
    client = make(tmp_path, queries={"calibration": answer})._build_app().test_client()

    rsp = client.get("/calibration?device=x&before=100")

    assert rsp.status_code == 200 and rsp.get_json() == {"bme688": {"state": "AAEC"}}
    assert asked == [{"device": "x", "before": "100"}]


def test_query_handler_none_is_a_404_and_value_error_a_400(tmp_path):
    def answer(args):
        if "before" not in args:
            raise ValueError("before is required")
        return None
    client = make(tmp_path, queries={"calibration": answer})._build_app().test_client()

    assert client.get("/calibration?before=1").status_code == 404
    rsp = client.get("/calibration")
    assert rsp.status_code == 400 and b"before is required" in rsp.data


def test_one_name_can_take_a_post_and_answer_a_get(tmp_path):
    seen = []
    server = make(tmp_path, ingest={"notes": seen.extend}, queries={"notes": lambda args: seen})
    client = server._build_app().test_client()

    assert client.post("/notes", json={"ts": 1}).status_code == 204
    assert client.get("/notes").get_json() == [{"ts": 1}]


def test_query_route_is_get_only_and_cannot_shadow_a_page(tmp_path):
    server = make(tmp_path, queries={"calibration": lambda args: {}})
    assert server._build_app().test_client().post("/calibration", json={}).status_code == 405
    with pytest.raises(ValueError, match="collide"):
        make(tmp_path, queries={"today.png": lambda args: {}})


# ---------- time ranges ----------

from epd_server.scheduling import Pools, TimeRangesSchedule  # noqa: E402
from epd_server.timeranges import TimeRanges, parse_hhmm  # noqa: E402

EVERY_5_MIN = TimeRanges([(parse_hhmm("00:00"), 300)], UTC)


def test_timeranges_drive_the_headers_and_the_index(tmp_path):
    (tmp_path / "today.png").write_bytes(PNG)
    (tmp_path / "hourly.png").write_bytes(PNG)
    sched = TimeRangesSchedule(EVERY_5_MIN, Pools({"a": ["today.png"], "b": ["hourly.png"]}, seed=1))
    server = make(tmp_path, schedule=sched)
    client = server._build_app().test_client()

    rsp = client.get("/today.png")
    assert rsp.status_code == 200
    assert 0 < int(rsp.headers["EPD-Next-Display-Refresh-Seconds"]) <= 300
    assert rsp.headers["EPD-Next-URL"].rsplit("/", 1)[1] in {"today.png", "hourly.png"}
    index = client.get("/").get_json()
    assert index["schedule"]["type"] == "timeranges" and index["schedule"]["order"] == ["a", "b"]

    with pytest.raises(ValueError, match="nope.png"):
        make(tmp_path, schedule=TimeRangesSchedule(EVERY_5_MIN, Pools({"a": ["nope.png"]})))


# ---------- firmware ----------

from epd_server.config import FirmwareSettings  # noqa: E402

BIN = b"\xe9" + b"\x00" * 63
CLIENT = {"EPD-Device": "my-display", "EPD-Device-Version": "v1.5.1"}


def with_firmware(tmp_path, version: str | None = "v1.6.0", **kw):
    """A server whose firmware directory holds one image."""
    fw_dir = tmp_path / "fw"
    fw_dir.mkdir(exist_ok=True)
    if version:
        (fw_dir / f"{version}.bin").write_bytes(BIN)
    settings = FirmwareSettings(enabled=True, dir=str(fw_dir), product="my-display",
                                offer_dev_builds=False, **kw)
    (tmp_path / "today.png").write_bytes(PNG)
    (tmp_path / "hourly.png").write_bytes(PNG)
    server = make(tmp_path, firmware=settings)
    server.app.config["TESTING"] = True
    return server, server.app.test_client()


def test_a_page_offers_the_update_to_the_board_it_is_for(tmp_path):
    _, client = with_firmware(tmp_path)

    rsp = client.get("/today.png", headers=CLIENT)

    assert rsp.headers["EPD-Server-Firmware-Version"] == "v1.6.0"
    assert rsp.headers["EPD-Server-Firmware-URL"] == "http://localhost/firmware.bin"
    assert rsp.data == PNG          # still the page


@pytest.mark.parametrize("headers", [
    {"EPD-Device": "other-display", "EPD-Device-Version": "v1.5.1"},   # another product
    {"EPD-Device": "my-display", "EPD-Device-Version": "v1.6.0"},      # already on it
    {"EPD-Device": "my-display", "EPD-Device-Version": "dev"},         # a developer build
    {"EPD-Device-Version": "v1.5.1"},                                     # no name
    {"EPD-Device": "my-display"},                                    # no version
    {},                                                                 # nothing at all
    {"User-Agent": "Mozilla/5.0 (Macintosh)"},                          # a browser
    {"User-Agent": "my-display/v1.5.1 (Inkplate10)"},                   # a User-Agent alone
])
def test_a_page_offers_nothing_to_anyone_else(tmp_path, headers):
    _, client = with_firmware(tmp_path)

    rsp = client.get("/today.png", headers=headers)

    assert "EPD-Server-Firmware-Version" not in rsp.headers
    assert "EPD-Server-Firmware-URL" not in rsp.headers


def test_a_stale_user_agent_does_not_override_the_headers(tmp_path):
    _, client = with_firmware(tmp_path)

    rsp = client.get("/today.png", headers={**CLIENT,
                                            "User-Agent": "my-display/v1.6.0 (Inkplate10)"})

    assert rsp.headers["EPD-Server-Firmware-Version"] == "v1.6.0"


def test_every_response_says_which_server_answered(tmp_path):
    from epd_server import __version__
    _, client = with_firmware(tmp_path)

    for path in ("/", "/today.png", "/firmware.bin"):
        assert client.get(path, headers=CLIENT).headers["EPD-Server-Version"] == __version__


def test_the_server_logs_the_client_that_asked(tmp_path, caplog):
    _, client = with_firmware(tmp_path)

    with caplog.at_level("INFO"):
        client.get("/today.png", headers=CLIENT)

    assert "my-display v1.5.1 asked for /today.png" in caplog.text


def test_no_firmware_headers_and_no_route_without_the_block(client):
    rsp = client.get("/today.png", headers=CLIENT)
    assert "EPD-Server-Firmware-Version" not in rsp.headers
    assert client.get("/firmware.bin").status_code == 404


def two_products(tmp_path, images, **kw):
    """A gated server at v0.3.1 holding images for a display and a sensor board."""
    fw_dir = tmp_path / "fw"
    for product, versions in images.items():
        (fw_dir / product).mkdir(parents=True, exist_ok=True)
        for v in versions:
            (fw_dir / product / f"{v}.bin").write_bytes(BIN + v.encode())
    settings = FirmwareSettings(enabled=True, dir=str(fw_dir), product="my-display",
                                offer_dev_builds=False, products=("my-display", "my-sensor"))
    (tmp_path / "today.png").write_bytes(PNG)
    (tmp_path / "hourly.png").write_bytes(PNG)
    server = make(tmp_path, firmware=settings, server_version="v0.3.1", version_gate=True,
                  ingest={"readings": lambda docs: None}, **kw)
    return server.app.test_client()


def board(name, version):
    return {"EPD-Device": name, "EPD-Device-Version": version}


def test_a_readings_post_carries_the_offer_for_its_own_product(tmp_path):
    client = two_products(tmp_path, {"my-display": ["v0.3.0"], "my-sensor": ["v0.3.0", "v0.3.2"]})

    rsp = client.post("/readings", json={"ts": 1}, headers=board("my-sensor", "v0.3.0"))

    assert rsp.status_code == 204
    assert rsp.headers["EPD-Server-Firmware-Version"] == "v0.3.2"
    url = rsp.headers["EPD-Server-Firmware-URL"]
    assert url == "http://localhost/firmware.bin?product=my-sensor&version=v0.3.2"
    image = client.get(url.replace("http://localhost", ""))
    assert image.status_code == 200 and image.data == BIN + b"v0.3.2"


def test_a_board_ahead_of_the_server_is_offered_the_servers_line(tmp_path, caplog):
    client = two_products(tmp_path, {"my-display": ["v0.3.0", "v0.4.0"]})

    with caplog.at_level("WARNING"):
        rsp = client.get("/today.png", headers=board("my-display", "v0.4.0"))

    assert rsp.headers["EPD-Server-Firmware-Version"] == "v0.3.0"
    assert "Offering my-display v0.4.0 an older firmware, v0.3.0: this server is v0.3.1" in caplog.text


def test_a_refused_board_hears_about_the_image_that_would_fix_it(tmp_path):
    refused = []
    client = two_products(tmp_path, {"my-sensor": ["v0.3.0"]},
                          on_refused=lambda name, version: refused.append((name, version)))

    rsp = client.post("/readings", json={"ts": 1}, headers=board("my-sensor", "v0.4.0"))

    assert rsp.status_code == 409
    assert rsp.headers["EPD-Server-Firmware-Version"] == "v0.3.0"
    assert refused == [("my-sensor", "v0.4.0")]


def test_no_image_for_the_servers_line_offers_nothing(tmp_path):
    client = two_products(tmp_path, {"my-sensor": ["v0.4.0"]})
    rsp = client.post("/readings", json={"ts": 1}, headers=board("my-sensor", "v0.3.0"))
    assert "EPD-Server-Firmware-Version" not in rsp.headers
    assert client.get("/firmware.bin?product=my-sensor").status_code == 404
    assert client.get("/firmware.bin?product=nobody&version=v0.4.0").status_code == 404


def test_the_image_is_served_with_its_length_and_md5(tmp_path):
    import hashlib
    _, client = with_firmware(tmp_path)

    rsp = client.get("/firmware.bin", headers=CLIENT)

    assert rsp.status_code == 200
    assert rsp.data == BIN
    assert rsp.headers["Content-Length"] == str(len(BIN))
    assert rsp.headers["x-MD5"] == hashlib.md5(BIN).hexdigest()
    assert rsp.mimetype == "application/octet-stream"


def test_a_board_that_already_runs_the_image_gets_a_304(tmp_path):
    _, client = with_firmware(tmp_path)

    rsp = client.get("/firmware.bin", headers={"x-ESP32-version": "v1.6.0"})

    assert rsp.status_code == 304 and rsp.data == b""
    assert client.get("/firmware.bin", headers={"x-ESP32-version": "v1.5.1"}).status_code == 200


def test_an_empty_firmware_directory_is_a_404_and_offers_nothing(tmp_path):
    _, client = with_firmware(tmp_path, version=None)

    assert client.get("/firmware.bin").status_code == 404
    assert "EPD-Server-Firmware-Version" not in client.get("/today.png", headers=CLIENT).headers


def test_an_image_copied_in_while_running_is_offered_at_the_next_fetch(tmp_path):
    server, client = with_firmware(tmp_path, version=None)

    assert "EPD-Server-Firmware-Version" not in client.get("/today.png", headers=CLIENT).headers
    (tmp_path / "fw" / "v1.6.0.bin").write_bytes(BIN)

    rsp = client.get("/today.png", headers=CLIENT)
    assert rsp.headers["EPD-Server-Firmware-Version"] == "v1.6.0"


def test_the_index_reports_the_image_it_holds(tmp_path):
    import hashlib
    _, client = with_firmware(tmp_path)

    body = client.get("/").get_json()

    assert body["firmware"] == {"version": "v1.6.0", "size": len(BIN),
                                "md5": hashlib.md5(BIN).hexdigest(), "product": "my-display"}


def test_the_release_watcher_runs_only_with_a_source(tmp_path, monkeypatch):
    from epd_server.config import FirmwareSource

    server, _ = with_firmware(tmp_path)
    server.shutdown_event = OneTickEvent()
    server.port = 0
    server.run(install_signal_handlers=False)
    assert server.release_watcher is None

    import threading
    started = threading.Event()
    monkeypatch.setattr("epd_server.firmware.ReleaseWatcher.run",
                        lambda self: started.set())
    settings = FirmwareSettings(True, str(tmp_path / "fw"), "my-display", False,
                                FirmwareSource("a/b", "firmware.bin", 3600, ""))
    server = make(tmp_path, port=0, firmware=settings)
    server.shutdown_event = OneTickEvent()
    server.run(install_signal_handlers=False)

    assert started.wait(2), "the watcher thread never ran"
    assert server.release_watcher is None   # stopped on shutdown


# ── The names on the wire ─────────────────────────────────────────────────

def client_for(tmp_path, **kw):
    (tmp_path / "today.png").write_bytes(PNG)
    (tmp_path / "hourly.png").write_bytes(PNG)
    server = make(tmp_path, **kw)
    server.app.config["TESTING"] = True
    return server.app.test_client()


def test_the_default_prefix_names_every_header(tmp_path):
    rsp = client_for(tmp_path).get("/today.png")

    assert int(rsp.headers["EPD-Next-Display-Refresh-Seconds"]) >= 0
    assert rsp.headers["EPD-Next-URL"].startswith("http://localhost/")
    assert rsp.headers["EPD-Server-Version"]
    assert int(rsp.headers["EPD-Server-Epoch-Seconds"]) > 0


def test_a_product_prefix_renames_every_header(tmp_path):
    rsp = client_for(tmp_path, header_prefix="Canary").get("/today.png")

    assert "Canary-Next-Display-Refresh-Seconds" in rsp.headers
    assert "Canary-Next-URL" in rsp.headers
    assert "Canary-Server-Version" in rsp.headers
    assert "Canary-Server-Epoch-Seconds" in rsp.headers
    assert "EPD-Next-Display-Refresh-Seconds" not in rsp.headers
    assert "EPD-Server-Version" not in rsp.headers


def test_the_server_sends_its_clock_on_every_response(tmp_path):
    client = client_for(tmp_path)

    for path in ("/", "/today.png"):
        sent = int(client.get(path).headers["EPD-Server-Epoch-Seconds"])
        assert abs(sent - time.time()) < 5


def test_the_sensor_poll_goes_on_every_response_when_the_project_sets_one(tmp_path):
    asked = []

    def poll(now, name):
        asked.append(now)
        return 240
    client = client_for(tmp_path, header_prefix="Canary", sensor_poll=poll,
                        ingest={"readings": lambda docs: None})

    for rsp in (client.get("/today.png"), client.post("/readings", json={"ts": 1})):
        assert rsp.headers["Canary-Next-Sensor-Poll-Seconds"] == "240"
        assert abs(asked[-1] - int(rsp.headers["Canary-Server-Epoch-Seconds"])) < 1


def test_each_board_gets_its_own_sensor_poll_and_none_goes_without(tmp_path):
    polls = {"canary-dock": 240, "canary-head": 1800}
    client = client_for(tmp_path, header_prefix="Canary",
                        sensor_poll=lambda now, name: polls.get(name))

    def poll_for(name):
        headers = {"Canary-Device": name} if name else {}
        return client.get("/today.png", headers=headers).headers.get(
            "Canary-Next-Sensor-Poll-Seconds")

    assert poll_for("canary-dock") == "240"
    assert poll_for("canary-head") == "1800"
    assert poll_for("weather-cal") is None
    assert poll_for(None) is None


def test_without_a_sensor_poll_there_is_no_header(tmp_path):
    rsp = client_for(tmp_path).get("/today.png")
    assert "EPD-Next-Sensor-Poll-Seconds" not in rsp.headers


def test_a_project_reports_its_own_version_not_the_package_one(tmp_path):
    from epd_server import __version__

    rsp = client_for(tmp_path, server_version="canary-v2.0.0").get("/today.png")

    assert rsp.headers["EPD-Server-Version"] == "canary-v2.0.0"
    assert rsp.headers["EPD-Server-Version"] != __version__


def test_the_header_prefix_cannot_be_empty(tmp_path):
    with pytest.raises(ValueError):
        client_for(tmp_path, header_prefix="  -  ")


def test_a_board_is_recognised_by_its_current_device_headers(tmp_path):
    _, client = with_firmware(tmp_path)

    rsp = client.get("/today.png", headers={"EPD-Device": "my-display",
                                            "EPD-Device-Version": "v1.5.1"})

    assert rsp.headers["EPD-Server-Firmware-Version"] == "v1.6.0"
    assert rsp.headers["EPD-Server-Firmware-Version"] == "v1.6.0"


# ── Version compatibility ─────────────────────────────────────────────────

def gated(tmp_path, **kw):
    received = []
    client = client_for(tmp_path, ingest={"readings": received.extend},
                        server_version="v0.2.2", **kw)
    return client, received


def post(client, version, name="canary-dock"):
    headers = {"EPD-Device": name}
    if version is not None:
        headers["EPD-Device-Version"] = version
    return client.post("/readings", json={"ts": 1, "device": name}, headers=headers)


def test_a_gated_server_refuses_a_board_it_cannot_work_with(tmp_path):
    client, received = gated(tmp_path, version_gate=True)

    rsp = post(client, "v0.3.0")

    assert rsp.status_code == 409
    assert rsp.get_json() == {"error": "version", "device": "v0.3.0", "server": "v0.2.2"}
    assert received == []


def test_a_gated_server_takes_a_board_it_can_work_with(tmp_path):
    client, received = gated(tmp_path, version_gate=True)

    assert post(client, "v0.2.9-3-gabc1234").status_code == 204
    assert len(received) == 1


def test_a_board_whose_version_cannot_be_read_is_let_through(tmp_path):
    """A development build must not have its readings silently refused."""
    client, received = gated(tmp_path, version_gate=True)

    assert post(client, "dev").status_code == 204
    assert post(client, None).status_code == 204
    assert len(received) == 2


def test_a_board_stating_the_old_header_names_is_judged_too(tmp_path):
    client, received = gated(tmp_path, version_gate=True)

    rsp = client.post("/readings", json={"ts": 1},
                      headers={"EPD-Device": "canary-dock", "EPD-Device-Version": "v0.3.0"})

    assert rsp.status_code == 409
    assert received == []


def test_without_the_gate_every_version_is_taken(tmp_path):
    client, received = gated(tmp_path)

    assert post(client, "v9.0.0").status_code == 204
    assert len(received) == 1


def test_the_gate_never_refuses_a_page(tmp_path):
    """A board the server refuses must still fetch pages, or it never learns of an update."""
    client, _ = gated(tmp_path, version_gate=True)

    rsp = client.get("/today.png", headers={"EPD-Device": "canary-head",
                                            "EPD-Device-Version": "v0.3.0"})

    assert rsp.status_code == 200
