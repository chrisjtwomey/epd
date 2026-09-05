"""A display with live data: two pages, one API, one schedule.

    pip install ../../server
    python3 server.py

Then open http://localhost:8080/now.png and .../forecast.png.
"""
from zoneinfo import ZoneInfo

from epd_server import DisplayServer
from epd_server.scheduling import Pools, TimesSchedule

from pages import ForecastPage, NowPage
from weather import OpenMeteo

TZ = ZoneInfo("Europe/Dublin")
# Dublin. Two numbers are the whole of "where this display is about".
LATITUDE, LONGITUDE = 53.3498, -6.2603

SIZE = {"width": 825, "height": 1200, "html_dir": "build", "png_dir": "build"}

# A schedule names a pool, not an image, and a pool of several images is read
# in turn. One image each here; add a second and the panel alternates.
pools = Pools({"conditions": ["now.png"], "outlook": ["forecast.png"]})

DisplayServer(
    pages=[NowPage("now", **SIZE), ForecastPage("forecast", **SIZE)],
    # Fetched only when a page that needs it is regenerated, and kept for
    # 15 minutes, so the two pages together cost one call.
    source=OpenMeteo(LATITUDE, LONGITUDE, TZ, ttl=900.0),
    # The weather itself through the day; the days ahead each evening.
    schedule=TimesSchedule(
        [
            ("07:30:00", "conditions"),
            ("12:30:00", "conditions"),
            ("18:30:00", "outlook"),
            ("22:00:00", "outlook"),
        ],
        pools,
        TZ,
    ),
    tz=TZ,
).run()
