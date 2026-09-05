"""The examples build and run, and the quickstart is one of them.

examples/minimal is the README's quickstart file for file: a reader may copy
either, so nothing may differ between them but the path to this repository,
and nothing else keeps them in step. The others must at least construct, and
examples/live-data's data source is exercised against a recorded response, so
none of this needs a network.
"""
import importlib
import runpy
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from epd_server import DisplayServer

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
README = (ROOT / "README.md").read_text()

FILES = ["server.py", "platformio.ini", "src/defaults.cpp", "src/main.cpp"]


@pytest.mark.parametrize("name", FILES)
def test_the_readme_shows_the_minimal_example_file(name):
    text = (EXAMPLES / "minimal" / name).read_text()
    # The example is inside this repository; the quickstart's project is beside it.
    text = text.replace("symlink://../../firmware", "symlink://../epd/firmware")
    assert text.strip() in README, f"{name} differs from the README's quickstart"


def run_example_server(example, monkeypatch, tmp_path) -> DisplayServer:
    """Run an example's server.py up to, but not including, run()."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(EXAMPLES / example))   # its own modules
    started = []
    monkeypatch.setattr(DisplayServer, "run", lambda self, *a, **kw: started.append(self))
    loaded = set(sys.modules)
    try:
        runpy.run_path(str(EXAMPLES / example / "server.py"), run_name="__main__")
    finally:
        # An example's modules have everyday names. Leaving them behind would
        # shadow anything of the same name a later test imports.
        for name in set(sys.modules) - loaded:
            del sys.modules[name]
    (server,) = started
    return server


@pytest.mark.parametrize("example", ["minimal", "ota"])
def test_the_clock_example_server_constructs(example, monkeypatch, tmp_path):
    server = run_example_server(example, monkeypatch, tmp_path)

    (page,) = server.pages
    assert page.name == "clock"
    page.template()   # the HTML, with no browser involved
    assert b'class="time"' in bytes(page.airium)


def test_the_ota_example_offers_images_to_the_panel_it_names(monkeypatch, tmp_path):
    server = run_example_server("ota", monkeypatch, tmp_path)

    assert server.firmware is not None and server.firmware.enabled
    assert server.firmware.product == "my-display"   # CLIENT_NAME in its platformio.ini
    assert server.firmware_store is not None and server.firmware_store.current() is None


# ── examples/live-data ────────────────────────────────────────────────────

# One Open-Meteo response, trimmed to two days. Recorded, so the parsing is
# tested against what the API actually sends.
FORECAST = {
    "current": {"time": "2026-09-06T00:15", "temperature_2m": 17.2,
                "relative_humidity_2m": 71, "weather_code": 3},
    "daily": {"time": ["2026-09-06", "2026-09-07"],
              "weather_code": [55, 61],
              "temperature_2m_max": [21.7, 19.1],
              "temperature_2m_min": [17.0, 11.5]},
}


@pytest.fixture
def live_data(monkeypatch):
    """examples/live-data's two modules, importable."""
    monkeypatch.syspath_prepend(str(EXAMPLES / "live-data"))
    loaded = set(sys.modules)
    # Imported by name, not by statement: they are on the path only for the
    # length of this fixture.
    yield importlib.import_module("weather"), importlib.import_module("pages")
    for name in set(sys.modules) - loaded:
        del sys.modules[name]


@pytest.fixture
def source(live_data, tmp_path):
    """The example's data source, answering from FORECAST, counting its calls."""
    weather, _ = live_data
    calls = []
    src = weather.OpenMeteo(
        53.3498, -6.2603, ZoneInfo("Europe/Dublin"),
        cache_path=str(tmp_path / "wx.json"),
        fetch=lambda url: (calls.append(url), FORECAST)[1],
    )
    src.calls = calls
    return src


def test_the_live_data_server_constructs(monkeypatch, tmp_path):
    server = run_example_server("live-data", monkeypatch, tmp_path)

    assert [p.name for p in server.pages] == ["now", "forecast"]
    assert server.schedule.pages() == {"now.png", "forecast.png"}


def test_both_datasets_come_from_one_fetch(source):
    conditions = source.conditions()
    outlook = source.outlook()

    assert conditions == {"temperature": 17, "humidity": 71, "text": "Cloudy"}
    assert outlook[0] == {"date": date(2026, 9, 6), "text": "Drizzle",
                          "high": 22, "low": 17}
    assert len(source.calls) == 1, "the second dataset should come from the cache"


def test_a_forced_refresh_fetches_again(source):
    source.conditions()
    source.invalidate()
    source.conditions()

    assert len(source.calls) == 2


def test_the_url_asks_for_what_the_pages_draw(source):
    source.conditions()

    (url,) = source.calls
    assert url.startswith("https://api.open-meteo.com/v1/forecast?")
    for asked in ["temperature_2m", "relative_humidity_2m", "weather_code",
                  "temperature_2m_max", "temperature_2m_min"]:
        assert asked in url


def test_an_unknown_weather_code_still_reads(live_data):
    weather, _ = live_data
    assert weather.describe(3) == "Cloudy"
    assert weather.describe(999) == "Unknown"


def test_each_page_draws_what_it_required(live_data, source):
    _, pages = live_data
    size = {"width": 825, "height": 1200}

    now = pages.NowPage("now", **size)
    now.template(**{name: source.datasets()[name]() for name in now.requires})
    assert b"17\xc2\xb0" in bytes(now.airium) and b"Cloudy" in bytes(now.airium)

    forecast = pages.ForecastPage("forecast", **size)
    forecast.template(**{name: source.datasets()[name]() for name in forecast.requires})
    html = bytes(forecast.airium)
    assert b"Today" in html and b"Monday" in html
