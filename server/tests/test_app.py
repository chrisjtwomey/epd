"""DisplayServer: routes, headers, schedule checks, regeneration, lifecycle."""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from epd_server.app import DisplayServer, align_process_timezone
from epd_server.config import MqttSettings
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
        assert int(rsp.headers["X-Next-Refresh-Seconds"]) >= 0
        assert rsp.headers["X-Next-URL"].startswith("http://localhost/")
        assert rsp.headers["X-Next-URL"].endswith(".png")


def test_missing_png_is_404(tmp_path):
    srv = make(tmp_path)  # no files written
    srv.app.config["TESTING"] = True
    with srv.app.test_client() as c:
        assert c.get("/today.png").status_code == 404


def test_unknown_route_is_404(client):
    assert client.get("/nope.png").status_code == 404


def test_index_lists_pages_schedule_and_next_wake(client):
    body = client.get("/").get_json()
    assert body["pages"] == ["today.png", "hourly.png"]
    assert body["schedule"] == [{"time": "09:00:00", "page": "today.png"},
                                {"time": "15:00:00", "page": "hourly.png"}]
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


class OneTickEvent:
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
    assert started == [(("h", 1883, "t"), {"client_id": "me"})]


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
    server = make(tmp_path, ingest={"readings": seen.append})
    client = server._build_app().test_client()

    rsp = client.post("/readings", json={"ts": 1, "co2_ppm": 640})

    assert rsp.status_code == 204 and rsp.data == b""
    assert seen == [{"ts": 1, "co2_ppm": 640}]


@pytest.mark.parametrize("data, content_type", [
    (b"not json", "application/json"),
    (b"[1, 2]", "application/json"),
    (b'{"ts": 1}', "text/plain"),
])
def test_ingest_rejects_anything_but_a_json_object(tmp_path, data, content_type):
    seen = []
    server = make(tmp_path, ingest={"readings": seen.append})
    client = server._build_app().test_client()

    rsp = client.post("/readings", data=data, content_type=content_type)

    assert rsp.status_code == 400 and seen == []


def test_ingest_handler_value_error_is_a_400_with_its_message(tmp_path):
    def reject(doc):
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
