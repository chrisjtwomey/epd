"""DST-correct wake and regeneration scheduling.

A *schedule* is a sorted list of ``(time_str, url_path)`` tuples, where
``time_str`` is ``HH:MM:SS`` wall-clock time in the server's timezone and
``url_path`` is the image the client should fetch at that wake.

All wall-clock arithmetic is anchored in the given ``tz`` so that DST
transitions are handled correctly. Callers computing "seconds from now"
must use :func:`seconds_until`, never ``next_dt - now``: Python's datetime
subtraction does naive wall-clock subtraction when both sides share a
tzinfo, silently dropping the one-hour shift across a DST transition.
"""
from __future__ import annotations

from datetime import datetime, timedelta, tzinfo as _tzinfo

Schedule = list[tuple[str, str]]


def validate_time_list(config_key: str, times) -> None:
    """Raise ``ValueError`` if any entry is not a valid ``HH:MM:SS`` string."""
    for t in times:
        try:
            datetime.strptime(t, "%H:%M:%S")
        except ValueError:
            raise ValueError(
                f"{config_key}: '{t}' is not a valid time — expected HH:MM:SS "
                f"(e.g. '09:00:00')"
            ) from None


def seconds_until(now: datetime, then: datetime) -> int:
    """Real seconds from ``now`` to ``then``, clamped at zero."""
    return max(0, int(then.timestamp() - now.timestamp()))


def next_wake(schedule: Schedule, tz: _tzinfo, now: datetime | None = None):
    """Return ``(wake_dt, url_path)`` for the next scheduled client wake.

    A slot equal to ``now`` counts as already passed.
    """
    if now is None:
        now = datetime.now(tz=tz)
    today = now.date()
    for time_str, url_path in schedule:
        t = datetime.strptime(time_str, "%H:%M:%S").time()
        dt = datetime.combine(today, t, tzinfo=tz)
        if dt > now:
            return dt, url_path
    tomorrow = today + timedelta(days=1)
    time_str, url_path = schedule[0]
    t = datetime.strptime(time_str, "%H:%M:%S").time()
    return datetime.combine(tomorrow, t, tzinfo=tz), url_path


def next_regen(schedule: Schedule, tz: _tzinfo, lead_seconds: int = 120,
               now: datetime | None = None):
    """Return ``(regen_dt, wake_dt, url_path)`` for the next regeneration.

    Regeneration fires ``lead_seconds`` before the corresponding client wake.
    The strict ``regen_dt > now`` check means that once a regen has fired,
    the next call advances to the following slot rather than re-triggering
    the same one.
    """
    if now is None:
        now = datetime.now(tz=tz)
    lead = timedelta(seconds=lead_seconds)
    today = now.date()
    for time_str, url_path in schedule:
        t = datetime.strptime(time_str, "%H:%M:%S").time()
        wake_dt = datetime.combine(today, t, tzinfo=tz)
        regen_dt = wake_dt - lead
        if regen_dt > now:
            return regen_dt, wake_dt, url_path
    tomorrow = today + timedelta(days=1)
    time_str, url_path = schedule[0]
    t = datetime.strptime(time_str, "%H:%M:%S").time()
    wake_dt = datetime.combine(tomorrow, t, tzinfo=tz)
    return wake_dt - lead, wake_dt, url_path


# ── Schedule objects ──────────────────────────────────────────────────────
#
# DisplayServer asks a schedule two things: when the client wakes next and
# for which page, and when to regenerate ahead of that. What shows is a
# pool of images read in turn; when it shows is the schedule's type.

import random
from typing import Mapping, Sequence

SECONDS_PER_DAY = 86400


class Pools:
    """Named pools of images.

    Each pool is read in turn on its own count, from a random start that
    moves every ``reshuffle_hours``, so a pass over several pools is never
    all of one shape. The starts come from the clock and a seed, so every
    process agrees and a restart changes nothing.
    """

    def __init__(self, pools: Mapping[str, Sequence[str]], reshuffle_hours: float = 3.0, seed: int = 0):
        if not pools:
            raise ValueError("at least one pool is needed")
        for name, pages in pools.items():
            if not pages:
                raise ValueError(f"pool {name!r} is empty")
        if reshuffle_hours <= 0:
            raise ValueError("reshuffle_hours must be positive")
        self.names = list(pools)
        self.pools = {name: list(pages) for name, pages in pools.items()}
        self.reshuffle_seconds = int(reshuffle_hours * 3600)
        self.seed = seed

    def page(self, name: str, visit: int, at: int) -> str:
        """The image for the ``visit``th reading of ``name``, at epoch ``at``."""
        pool = self.pools[name]
        block = at // self.reshuffle_seconds
        i = self.names.index(name)
        offset = random.Random(self.seed * 1_000_003 + block * 1_009 + i).randrange(len(pool))
        return pool[(visit + offset) % len(pool)]

    def pages(self, names=None) -> set[str]:
        names = self.names if names is None else names
        return {p for n in names for p in self.pools[n]}

    def describe(self) -> dict:
        return {name: list(pages) for name, pages in self.pools.items()}


class WakeSchedule:
    """What DisplayServer needs from a schedule."""

    tz: _tzinfo

    def next_wake(self, now: datetime | None = None) -> tuple[datetime, str]:
        raise NotImplementedError

    def next_regen(self, lead_seconds: int = 120, now: datetime | None = None) -> tuple[datetime, datetime, str]:
        raise NotImplementedError

    def pages(self) -> set[str]:
        """Every image the schedule can name."""
        raise NotImplementedError

    def describe(self) -> dict:
        """For the index route."""
        raise NotImplementedError


class TimesSchedule(WakeSchedule):
    """Fixed wall-clock wake times, each naming a pool."""

    def __init__(self, times: Schedule, pools: Pools, tz: _tzinfo):
        if not times:
            raise ValueError("a times schedule needs at least one wake time")
        validate_time_list("display.schedule", [t for t, _ in times])
        unknown = sorted({n for _, n in times} - set(pools.names))
        if unknown:
            raise ValueError(f"schedule names pools {unknown} that display.pools does not define")
        self.times = sorted(times, key=lambda x: x[0])
        self.pools = pools
        self.tz = tz

    def _page(self, wake_dt: datetime, name: str) -> str:
        slots = [t for t, n in self.times if n == name]
        idx = slots.index(wake_dt.strftime("%H:%M:%S"))
        visit = wake_dt.date().toordinal() * len(slots) + idx
        return self.pools.page(name, visit, int(wake_dt.timestamp()))

    def next_wake(self, now=None):
        wake_dt, name = next_wake(self.times, self.tz, now=now)
        return wake_dt, self._page(wake_dt, name)

    def next_regen(self, lead_seconds=120, now=None):
        regen_dt, wake_dt, name = next_regen(self.times, self.tz, lead_seconds=lead_seconds, now=now)
        return regen_dt, wake_dt, self._page(wake_dt, name)

    def pages(self):
        return self.pools.pages({n for _, n in self.times})

    def describe(self):
        return {"type": "times", "times": [{"time": t, "pool": n} for t, n in self.times],
                "pools": self.pools.describe()}

    def __iter__(self):
        return iter(self.times)

    def __len__(self):
        return len(self.times)


class IntervalSchedule(WakeSchedule):
    """A page every ``every`` seconds, visiting the pools in ``order``."""

    def __init__(self, every: int, pools: Pools, tz: _tzinfo, order: Sequence[str] | None = None):
        if every <= 0 or SECONDS_PER_DAY % every:
            raise ValueError(f"every must divide a day of {SECONDS_PER_DAY} seconds (got {every})")
        order = list(order) if order else list(pools.names)
        unknown = sorted(set(order) - set(pools.names))
        if unknown:
            raise ValueError(f"order names pools {unknown} that display.pools does not define")
        self.every = every
        self.pools = pools
        self.tz = tz
        self.order = order

    def page_for_slot(self, slot: int) -> str:
        """The page for the ``slot``th interval since the epoch."""
        name = self.order[slot % len(self.order)]
        return self.pools.page(name, slot // len(self.order), slot * self.every)

    def _now(self, now):
        return now if now is not None else datetime.now(tz=self.tz)

    def next_wake(self, now=None):
        now = self._now(now)
        slot = int(now.timestamp() // self.every) + 1
        return datetime.fromtimestamp(slot * self.every, self.tz), self.page_for_slot(slot)

    def next_regen(self, lead_seconds=120, now=None):
        now = self._now(now)
        slot = int((now.timestamp() + lead_seconds) // self.every) + 1
        wake = datetime.fromtimestamp(slot * self.every, self.tz)
        return wake - timedelta(seconds=lead_seconds), wake, self.page_for_slot(slot)

    def pages(self):
        return self.pools.pages(set(self.order))

    def describe(self):
        return {"type": "interval", "every": self.every, "order": list(self.order),
                "pools": self.pools.describe()}
