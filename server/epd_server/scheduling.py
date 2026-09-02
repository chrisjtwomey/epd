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
