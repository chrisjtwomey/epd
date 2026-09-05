"""Open-Meteo, as two datasets a page can draw.

No account and no key: a latitude and a longitude are the whole
configuration. Both datasets come out of one response, so a regeneration
that draws both pages still makes one call, and the disk cache means a
restart makes none until the stored answer expires.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Callable

from epd_server.cache import DiskCache
from epd_server.source import DataSource

API = "https://api.open-meteo.com/v1/forecast"
CACHE_KEY = "forecast"

# Open-Meteo reports the weather as a WMO code. A panel wants a word, and
# neighbouring codes differ by more detail than a five-day column can show.
CONDITIONS = [
    (0, 0, "Clear"),
    (1, 3, "Cloudy"),
    (45, 48, "Fog"),
    (51, 57, "Drizzle"),
    (61, 67, "Rain"),
    (71, 77, "Snow"),
    (80, 82, "Showers"),
    (85, 86, "Snow showers"),
    (95, 99, "Thunderstorm"),
]


def describe(code: int) -> str:
    """The WMO weather code as a word."""
    for low, high, text in CONDITIONS:
        if low <= code <= high:
            return text
    return "Unknown"


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=20) as rsp:
        return json.load(rsp)


class OpenMeteo(DataSource):
    """Current conditions and a five-day outlook, from one public API.

    Args:
        latitude, longitude: where to report on.
        tz: the timezone the daily figures are grouped by.
        cache_path: the file a fetched response is kept in.
        ttl: how long a stored response is used before fetching again.
        fetch: takes a URL, returns the parsed JSON. Replaced in tests, so
            nothing here needs a network to be exercised.
    """

    def __init__(
        self,
        latitude: float,
        longitude: float,
        tz,
        cache_path: str = ".weather-cache.json",
        ttl: float = 900.0,
        fetch: Callable[[str], Any] = _get,
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.tz = tz
        self.ttl = ttl
        self.fetch = fetch
        self._cache = DiskCache(cache_path, "open-meteo")

    # ── DataSource ────────────────────────────────────────────────────────

    def datasets(self) -> dict[str, Callable[[], Any]]:
        return {"conditions": self.conditions, "outlook": self.outlook}

    def invalidate(self) -> None:
        self._cache.delete(CACHE_KEY)

    # ── The datasets themselves ───────────────────────────────────────────

    def conditions(self) -> dict:
        """What it is doing outside now."""
        now = self._payload()["current"]
        return {
            "temperature": round(now["temperature_2m"]),
            "humidity": now["relative_humidity_2m"],
            "text": describe(now["weather_code"]),
        }

    def outlook(self) -> list[dict]:
        """One entry per day, soonest first."""
        daily = self._payload()["daily"]
        # Open-Meteo answers with one array per field. A page wants one day
        # per entry, so the arrays are zipped back together here instead of
        # in every page that draws them.
        return [
            {
                "date": date.fromisoformat(day),
                "text": describe(code),
                "high": round(high),
                "low": round(low),
            }
            for day, code, high, low in zip(
                daily["time"],
                daily["weather_code"],
                daily["temperature_2m_max"],
                daily["temperature_2m_min"],
            )
        ]

    # ── The one call behind both ──────────────────────────────────────────

    def _payload(self) -> dict:
        """The stored response, fetching a new one when it has expired."""
        stored = self._cache.get(CACHE_KEY, ttl=self.ttl)
        if stored is not None:
            return stored
        payload = self.fetch(self._url())
        # Stored as it arrived. Anything built from it, a date object for
        # one, would not survive the trip through JSON.
        self._cache.set(CACHE_KEY, payload)
        return payload

    def _url(self) -> str:
        query = urllib.parse.urlencode(
            {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "current": "temperature_2m,relative_humidity_2m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": str(self.tz),
                "forecast_days": 5,
            }
        )
        return f"{API}?{query}"
