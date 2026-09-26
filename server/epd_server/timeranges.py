"""When something happens on the wall clock: ranges round the clock, each
with its own interval, and a week of them, a day of ranges for each group of
days.

A day of time ranges covers the whole day. Each range runs from its start to
the next range's, and the last runs past midnight to the first, so there is
no gap and no overlap; one range is the whole day. An interval of 0 turns its
range off. A slot is a local time in a range that is on, whose seconds past
midnight are a multiple of that range's interval: :00, :05, :10 ... for five
minutes, the hour and the half hour for thirty.

In a week each day stands alone: before a day's first start its own last
range runs, not the last range of the day before, so a day's ranges say all
that happens on it.

The ranges are judged in local time, one minute at a time, rather than by
working out where their edges fall. Some clocks change at 01:00: in spring
01:00 to 02:00 never happens, and in autumn it happens twice. Stepping
through the minutes and asking of each which range it is in gets both right
without a special case.
"""
from __future__ import annotations

import math
from datetime import datetime, time as clock_time, tzinfo

# The slots fall on whole minutes, so every interval is a whole number of them.
MINUTE = 60
DAY = 24 * 60 * MINUTE
# Two days of minutes: further than any gap between two slots of a day of
# ranges can be.
LOOK_AHEAD_MINUTES = 2 * 24 * 60
# More ranges than a day needs, and few enough to set on one screen.
MAX_RANGES = 8
# The days of the week as config.yaml names them, Monday first, as
# datetime.weekday() counts them.
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_hhmm(text: str) -> clock_time:
    """``"01:00"`` as a time of day.

    Raises:
        ValueError: it is not ``HH:MM``.
    """
    try:
        hours, minutes = str(text).split(":")
        return clock_time(int(hours), int(minutes))
    except ValueError:
        raise ValueError(f"{text!r} is not a time of day as HH:MM") from None


def check_interval(seconds, name: str) -> int:
    """``seconds`` as a range's interval.

    Raises:
        ValueError: it is not 0 or a whole number of minutes up to a day,
            named by ``name``.
    """
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 <= seconds <= DAY \
            or seconds % MINUTE:
        raise ValueError(f"{name} must be 0, for off, or a whole number of minutes up to "
                         f"a day, in seconds, not {seconds!r}")
    return seconds


class Slots:
    """The slots of a schedule in epoch seconds, found a minute at a time
    from :meth:`is_slot`."""

    tz: tzinfo
    # How far to look for a slot before deciding there is none.
    look_ahead = LOOK_AHEAD_MINUTES

    def is_slot(self, minute: int) -> bool:
        """Whether the whole minute at epoch seconds ``minute`` is a slot."""
        raise NotImplementedError

    def next_slot(self, t: float) -> int | None:
        """The first slot after ``t``, in epoch seconds; one at ``t`` has
        passed. None when no range holds a slot."""
        minute = (math.floor(t) // MINUTE + 1) * MINUTE
        for _ in range(self.look_ahead):
            if self.is_slot(minute):
                return minute
            minute += MINUTE
        return None

    def seconds_until_next(self, now: float) -> int | None:
        """Whole seconds until the first slot after ``now``, rounded up so a
        board that waits this long is never early for it. None when no range
        holds a slot."""
        slot = self.next_slot(now)
        return None if slot is None else max(1, math.ceil(slot - now))

    def slot_before(self, t: float) -> int | None:
        """The latest slot at or before ``t``, or None when no range holds one."""
        minute = math.floor(t) // MINUTE * MINUTE
        for _ in range(self.look_ahead):
            if self.is_slot(minute):
                return minute
            minute -= MINUTE
        return None


class TimeRanges(Slots):
    """A day of time ranges, and the slots in them.

    Args:
        ranges: each range's start and interval in seconds, 0 for off, in
            any order.
        tz: the zone the day is in.
        name: the config key the ranges come from, which each message
            starts with.

    Raises:
        ValueError: no ranges, more than MAX_RANGES, two that start at the
            same time, or an interval that is not 0 or a whole number of
            minutes up to a day.
    """

    def __init__(self, ranges: list[tuple[clock_time, int]], tz: tzinfo, name: str = "ranges"):
        if not ranges:
            raise ValueError(f"{name} needs at least one range")
        if len(ranges) > MAX_RANGES:
            raise ValueError(f"{name} has {len(ranges)} ranges; the most is {MAX_RANGES}")
        starts = [start for start, _ in ranges]
        for start in starts:
            if starts.count(start) > 1:
                raise ValueError(f"{name} has two ranges from {start.strftime('%H:%M')}")
        self.ranges = sorted((start, check_interval(every, f"{name} every"))
                             for start, every in ranges)
        self.tz = tz
        self.name = name

    @classmethod
    def from_config(cls, value, tz: tzinfo, name: str) -> TimeRanges:
        """The ranges a config value gives: a list of ``{from, every}``.

        Raises:
            ValueError: the value is not such a list, or the ranges cannot work.
        """
        if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
            raise ValueError(f"{name} must be a list of ranges, each {{from: \"HH:MM\", every: "
                             f"seconds}}")
        ranges = []
        for r in value:
            if set(r) != {"from", "every"}:
                raise ValueError(f"{name}: each range has exactly from and every, not "
                                 f"{', '.join(map(str, r)) or 'nothing'}")
            try:
                start = parse_hhmm(r["from"])
            except ValueError as exc:
                raise ValueError(f"{name}: {exc}") from None
            ranges.append((start, r["every"]))
        return cls(ranges, tz, name)

    def every_at(self, t: clock_time) -> int:
        """The interval of the range a time of day is in; 0 when it is off."""
        current = self.ranges[-1][1]   # before the first start, the last range runs on
        for start, every in self.ranges:
            if start > t:
                break
            current = every
        return current

    def is_slot_at(self, t: clock_time) -> bool:
        """Whether a time of day, in whole minutes, is a slot."""
        step = self.every_at(t)
        return step > 0 and (t.hour * 3600 + t.minute * 60) % step == 0

    def is_slot(self, minute: int) -> bool:
        """Whether the whole minute at epoch seconds ``minute`` is a slot."""
        return self.is_slot_at(datetime.fromtimestamp(minute, self.tz).time())

    def slots_a_day(self) -> int:
        """How many slots a day without a clock change has."""
        return sum(self.is_slot_at(clock_time(m // 60, m % 60)) for m in range(DAY // MINUTE))

    def describe(self) -> list[dict]:
        """The ranges as config.yaml writes them, from the earliest start."""
        return [{"from": start.strftime("%H:%M"), "every": every} for start, every in self.ranges]


class Week(Slots):
    """Groups of days of the week, each with a day of time ranges.

    Args:
        groups: each group's days, as datetime.weekday() numbers them, and
            its ranges. Each day is in exactly one group.
        tz: the zone the days are in.
        name: the config key the week comes from, which each message
            starts with.

    Raises:
        ValueError: no groups, a group with no days, or a day in two
            groups or in none.
    """

    # A week and a day of minutes: further than any gap between two slots
    # can be, even with days that have none.
    look_ahead = 8 * 24 * 60

    def __init__(self, groups: list[tuple[frozenset[int], TimeRanges]], tz: tzinfo,
                 name: str = "week"):
        if not groups:
            raise ValueError(f"{name} needs at least one group of days")
        self._by_day: dict[int, TimeRanges] = {}
        for days, ranges in groups:
            if not days:
                raise ValueError(f"{name} has a group with no days")
            for day in days:
                if day in self._by_day:
                    raise ValueError(f"{name} has {DAYS[day]} in two groups")
                self._by_day[day] = ranges
        missing = [DAYS[d] for d in range(7) if d not in self._by_day]
        if missing:
            raise ValueError(f"{name} has no group for {', '.join(missing)}; each day needs one")
        self.groups = [(frozenset(days), ranges) for days, ranges in groups]
        self.tz = tz
        self.name = name
        self._per_day = [self._by_day[d].slots_a_day() for d in range(7)]

    @classmethod
    def every_day(cls, ranges: TimeRanges) -> Week:
        """A week whose days all have ``ranges``."""
        return cls([(frozenset(range(7)), ranges)], ranges.tz, ranges.name)

    @classmethod
    def from_config(cls, value, tz: tzinfo, name: str) -> Week:
        """The week a config value gives: a list of ``{days, ranges}``, the
        days named as :data:`DAYS` names them.

        Raises:
            ValueError: the value is not such a list, or the week cannot work.
        """
        if not isinstance(value, list) or not all(isinstance(g, dict) for g in value):
            raise ValueError(f"{name} must be a list of groups, each {{days: [mon, ...], "
                             f"ranges: [...]}}")
        groups = []
        for i, group in enumerate(value):
            if set(group) != {"days", "ranges"}:
                raise ValueError(f"{name}: each group has exactly days and ranges, not "
                                 f"{', '.join(map(str, group)) or 'nothing'}")
            days = group["days"]
            if not isinstance(days, list) or not all(d in DAYS for d in days):
                raise ValueError(f"{name}[{i}].days must be a list of {', '.join(DAYS)}")
            if len(set(days)) != len(days):
                raise ValueError(f"{name}[{i}].days names a day twice")
            ranges = TimeRanges.from_config(group["ranges"], tz, f"{name}[{i}].ranges")
            groups.append((frozenset(DAYS.index(d) for d in days), ranges))
        return cls(groups, tz, name)

    def on(self, weekday: int) -> TimeRanges:
        """The ranges of a day of the week, as datetime.weekday() numbers it."""
        return self._by_day[weekday]

    def is_slot(self, minute: int) -> bool:
        local = datetime.fromtimestamp(minute, self.tz)
        return self._by_day[local.weekday()].is_slot_at(local.time())

    def slots_on(self, weekday: int) -> int:
        """How many slots that day of the week has, without a clock change."""
        return self._per_day[weekday]

    def slots_a_week(self) -> int:
        """How many slots a week without a clock change has."""
        return sum(self._per_day)

    def next_slot(self, t: float) -> int | None:
        return super().next_slot(t) if self.slots_a_week() else None

    def slot_before(self, t: float) -> int | None:
        return super().slot_before(t) if self.slots_a_week() else None

    def describe(self) -> list[dict]:
        """The groups as config.yaml writes them, each day named, Monday first."""
        return [{"days": [DAYS[d] for d in sorted(days)], "ranges": ranges.describe()}
                for days, ranges in self.groups]


def in_window(t: clock_time, start: clock_time, end: clock_time) -> bool:
    """Whether a time of day falls from ``start`` up to ``end``, which may be
    past midnight."""
    if start < end:
        return start <= t < end
    return t >= start or t < end
