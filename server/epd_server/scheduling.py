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
# for which page, and when to regenerate ahead of that. A time list answers
# from its fixed slots; a pool schedule decides at the moment it is asked.

import random
from typing import Mapping, Sequence

SECONDS_PER_DAY = 86400


class WakeSchedule:
    """What DisplayServer needs from a schedule."""

    tz: _tzinfo

    def next_wake(self, now: datetime | None = None) -> tuple[datetime, str]:
        raise NotImplementedError

    def next_regen(self, lead_seconds: int = 120, now: datetime | None = None) -> tuple[datetime, datetime, str]:
        raise NotImplementedError

    def pages(self) -> set[str]:
        """Every page the schedule can name."""
        raise NotImplementedError

    def describe(self) -> list[dict]:
        """For the index route."""
        raise NotImplementedError


class TimeListSchedule(WakeSchedule):
    """Fixed wall-clock slots: the ``(HH:MM:SS, page)`` list."""

    def __init__(self, schedule: Schedule, tz: _tzinfo):
        if not schedule:
            raise ValueError("a time list schedule needs at least one slot")
        self.schedule = list(schedule)
        self.tz = tz

    def next_wake(self, now=None):
        return next_wake(self.schedule, self.tz, now=now)

    def next_regen(self, lead_seconds=120, now=None):
        return next_regen(self.schedule, self.tz, lead_seconds=lead_seconds, now=now)

    def pages(self):
        return {p for _, p in self.schedule}

    def describe(self):
        return [{"time": t, "page": p} for t, p in self.schedule]

    def __iter__(self):
        return iter(self.schedule)

    def __len__(self):
        return len(self.schedule)


class PoolSchedule(WakeSchedule):
    """A page every ``every`` seconds, round-robin over the pools, and
    round-robin inside each pool on its own count.

    Each pool starts at a random place in its list, so one pass is never
    all of one shape, and the starting places change every
    ``reshuffle_hours``. The randomness is seeded from the wall clock, so
    every process agrees and a restart changes nothing.
    """

    def __init__(self, every: int, pools: Mapping[str, Sequence[str]], tz: _tzinfo,
                 reshuffle_hours: float = 3.0, seed: int = 0):
        if every <= 0 or SECONDS_PER_DAY % every:
            raise ValueError(f"every must divide a day of {SECONDS_PER_DAY} seconds (got {every})")
        if not pools:
            raise ValueError("a pool schedule needs at least one pool")
        for name, pages in pools.items():
            if not pages:
                raise ValueError(f"pool {name!r} is empty")
        if reshuffle_hours <= 0:
            raise ValueError("reshuffle_hours must be positive")
        self.every = every
        self.names = list(pools)
        self.pools = {name: list(pages) for name, pages in pools.items()}
        self.tz = tz
        self.reshuffle_seconds = int(reshuffle_hours * 3600)
        self.seed = seed

    def page_for_slot(self, slot: int) -> str:
        """The page for the ``slot``th interval since the epoch."""
        i = slot % len(self.names)
        pool = self.pools[self.names[i]]
        visit = slot // len(self.names)
        block = (slot * self.every) // self.reshuffle_seconds
        offset = random.Random(self.seed * 1_000_003 + block * 1_009 + i).randrange(len(pool))
        return pool[(visit + offset) % len(pool)]

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
        return {p for pages in self.pools.values() for p in pages}

    def describe(self):
        return [{"pool": name, "pages": self.pools[name]} for name in self.names]
