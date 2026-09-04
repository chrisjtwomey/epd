"""DST-correct scheduling maths in epd_server.scheduling."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from epd_server.scheduling import (
    next_regen,
    next_wake,
    seconds_until,
    validate_time_list,
)


DUB = ZoneInfo("Europe/Dublin")
WAKE_SCHEDULE = [
    ("09:00:00", "today.png"),
    ("15:00:00", "daily.png"),
    ("21:00:00", "today.png"),
]
REGEN_LEAD = 120  # seconds


def real_seconds_until(now, next_dt):
    """Timestamp arithmetic, same as the daemon. Plain `next_dt - now` does
    naive wall-clock subtraction when both sides share a tzinfo and silently
    drops the 1h shift across a DST transition."""
    return next_dt.timestamp() - now.timestamp()


# ============================================================
# next_wake
# ============================================================

def test_same_day_next_wake_is_today():
    now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=DUB)
    nxt, url = next_wake(WAKE_SCHEDULE, DUB, now=now)
    assert nxt == datetime(2026, 7, 1, 15, 0, 0, tzinfo=DUB)
    assert url == "daily.png"
    assert real_seconds_until(now, nxt) == 5 * 3600


def test_rolls_over_to_tomorrow_after_last_wake():
    now = datetime(2026, 7, 1, 23, 30, 0, tzinfo=DUB)
    nxt, url = next_wake(WAKE_SCHEDULE, DUB, now=now)
    assert nxt == datetime(2026, 7, 2, 9, 0, 0, tzinfo=DUB)
    assert url == "today.png"


def test_rolls_over_at_exact_match():
    # Equal-to-wake-time means we've already hit it; advance to next.
    now = datetime(2026, 7, 1, 15, 0, 0, tzinfo=DUB)
    nxt, url = next_wake(WAKE_SCHEDULE, DUB, now=now)
    assert nxt == datetime(2026, 7, 1, 21, 0, 0, tzinfo=DUB)
    assert url == "today.png"


def test_one_second_before_wake():
    now = datetime(2026, 7, 1, 8, 59, 59, tzinfo=DUB)
    nxt, url = next_wake(WAKE_SCHEDULE, DUB, now=now)
    assert nxt == datetime(2026, 7, 1, 9, 0, 0, tzinfo=DUB)
    assert url == "today.png"
    assert real_seconds_until(now, nxt) == 1


def test_fall_back_eve_delta_is_12_real_hours():
    """DST fall-back: Sun 25 Oct 2026 at 02:00 IST -> 01:00 GMT.
    From Sat 22:00 IST to Sun 09:00 GMT is 12 real hours (11 wall + 1 DST)."""
    now = datetime(2026, 10, 24, 22, 0, 0, tzinfo=DUB)
    nxt, _ = next_wake(WAKE_SCHEDULE, DUB, now=now)
    assert nxt.utcoffset() == timedelta(0)                # GMT post-fall-back
    assert real_seconds_until(now, nxt) == 12 * 3600


def test_spring_forward_eve_delta_is_10_real_hours():
    """DST spring-forward: Sun 28 Mar 2027 at 01:00 GMT -> 02:00 IST.
    From Sat 22:00 GMT to Sun 09:00 IST is 10 real hours (11 wall - 1 DST)."""
    now = datetime(2027, 3, 27, 22, 0, 0, tzinfo=DUB)
    nxt, _ = next_wake(WAKE_SCHEDULE, DUB, now=now)
    assert nxt.utcoffset() == timedelta(hours=1)          # IST post-spring-forward
    assert real_seconds_until(now, nxt) == 10 * 3600


def test_single_wake_rolls_to_tomorrow_when_all_past():
    now = datetime(2026, 7, 1, 23, 0, 0, tzinfo=DUB)
    nxt, url = next_wake([("09:00:00", "today.png")], DUB, now=now)
    assert nxt == datetime(2026, 7, 2, 9, 0, 0, tzinfo=DUB)
    assert url == "today.png"


def test_uses_default_now_when_omitted():
    """Smoke test: calling without `now` produces a tz-aware result in the future."""
    nxt, url = next_wake(WAKE_SCHEDULE, DUB)
    assert nxt.tzinfo is DUB
    assert nxt > datetime.now(tz=DUB)
    assert isinstance(url, str)


# ============================================================
# seconds_until
# ============================================================

def test_seconds_until_uses_real_time_across_dst():
    now = datetime(2026, 10, 24, 22, 0, 0, tzinfo=DUB)
    then = datetime(2026, 10, 25, 9, 0, 0, tzinfo=DUB)
    assert seconds_until(now, then) == 12 * 3600


def test_seconds_until_clamps_at_zero():
    now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=DUB)
    assert seconds_until(now, now - timedelta(seconds=5)) == 0


# ============================================================
# next_regen
# ============================================================

def test_next_regen_fires_2_min_before_next_wake():
    now = datetime(2026, 7, 1, 10, 0, 0, tzinfo=DUB)
    regen_dt, wake_dt, url = next_regen(WAKE_SCHEDULE, DUB, lead_seconds=REGEN_LEAD, now=now)
    assert wake_dt == datetime(2026, 7, 1, 15, 0, 0, tzinfo=DUB)
    assert regen_dt == datetime(2026, 7, 1, 14, 58, 0, tzinfo=DUB)
    assert url == "daily.png"


def test_next_regen_advances_after_regen_fires():
    # Simulate: regen just fired at 14:58 for the 15:00 wake.
    # now == regen_dt, so strict > check must skip to the 21:00 slot.
    now = datetime(2026, 7, 1, 14, 58, 0, tzinfo=DUB)
    regen_dt, wake_dt, url = next_regen(WAKE_SCHEDULE, DUB, lead_seconds=REGEN_LEAD, now=now)
    assert wake_dt == datetime(2026, 7, 1, 21, 0, 0, tzinfo=DUB)
    assert regen_dt == datetime(2026, 7, 1, 20, 58, 0, tzinfo=DUB)
    assert url == "today.png"


def test_next_regen_wraps_to_tomorrow():
    now = datetime(2026, 7, 1, 22, 0, 0, tzinfo=DUB)
    regen_dt, wake_dt, url = next_regen(WAKE_SCHEDULE, DUB, lead_seconds=REGEN_LEAD, now=now)
    assert wake_dt == datetime(2026, 7, 2, 9, 0, 0, tzinfo=DUB)
    assert regen_dt == datetime(2026, 7, 2, 8, 58, 0, tzinfo=DUB)
    assert url == "today.png"


def test_next_regen_single_slot_wraps():
    schedule = [("09:00:00", "today.png")]
    now = datetime(2026, 7, 1, 9, 30, 0, tzinfo=DUB)
    regen_dt, wake_dt, url = next_regen(schedule, DUB, lead_seconds=REGEN_LEAD, now=now)
    assert wake_dt == datetime(2026, 7, 2, 9, 0, 0, tzinfo=DUB)
    assert regen_dt == datetime(2026, 7, 2, 8, 58, 0, tzinfo=DUB)


# ============================================================
# validate_time_list
# ============================================================

def test_validate_time_list_accepts_hhmmss():
    validate_time_list("display.schedule", ["00:00:00", "09:30:00", "23:59:59"])


@pytest.mark.parametrize("bad", ["9:00", "09:00", "25:00:00", "09:60:00", "nine", ""])
def test_validate_time_list_rejects_malformed(bad):
    with pytest.raises(ValueError, match="display.schedule"):
        validate_time_list("display.schedule", ["09:00:00", bad])


# ---------- pools and schedule objects ----------

from epd_server.scheduling import IntervalSchedule, Pools, TimesSchedule  # noqa: E402

DUB = ZoneInfo("Europe/Dublin")
POOL_LISTS = {"co2": ["breathe.png", "co2-trace.png", "co2-delta.png"],
              "air": ["air.png", "air-trace.png"],
              "day": ["day.png"]}
POOLS = Pools(POOL_LISTS, reshuffle_hours=3, seed=1)
BLOCK = 3 * 3600


def test_pools_are_read_in_turn_from_a_start_that_holds_within_a_block():
    at = 100 * BLOCK
    pages = [POOLS.page("co2", v, at + v * 300) for v in range(6)]
    pool = POOL_LISTS["co2"]
    start = pool.index(pages[0])
    assert pages == [pool[(start + k) % 3] for k in range(6)]
    assert POOLS.page("day", 5, at) == "day.png"
    assert POOLS.pages({"day", "air"}) == {"day.png", "air.png", "air-trace.png"}
    assert POOLS.describe() == POOL_LISTS


def test_pool_starts_move_between_blocks_and_agree_between_processes():
    def starts(pools):
        return [POOL_LISTS["co2"].index(pools.page("co2", 0, b * BLOCK)) for b in range(40)]
    assert len(set(starts(POOLS))) > 1
    assert starts(POOLS) == starts(Pools(POOL_LISTS, reshuffle_hours=3, seed=1))
    assert starts(POOLS) != starts(Pools(POOL_LISTS, reshuffle_hours=3, seed=2))


@pytest.mark.parametrize("pools, hours", [({}, 3), ({"x": []}, 3), ({"x": ["a.png"]}, 0)])
def test_pools_reject_bad_shapes(pools, hours):
    with pytest.raises(ValueError):
        Pools(pools, reshuffle_hours=hours)


def test_times_schedule_names_pools_and_reads_each_in_turn():
    steady = Pools(POOL_LISTS, reshuffle_hours=24 * 365, seed=1)   # one block: no reshuffle
    ts = TimesSchedule([("21:00:00", "co2"), ("09:00:00", "co2"), ("15:00:00", "air")], steady, DUB)
    assert list(ts) == [("09:00:00", "co2"), ("15:00:00", "air"), ("21:00:00", "co2")]
    seq = [ts.next_wake(datetime(2026, 9, d, h, 0, tzinfo=DUB) - timedelta(minutes=1))[1]
           for d, h in ((4, 9), (4, 21), (5, 9), (5, 21))]
    pool = POOL_LISTS["co2"]
    start = pool.index(seq[0])
    assert seq == [pool[(start + k) % 3] for k in range(4)]
    wake, page = ts.next_wake(datetime(2026, 9, 4, 10, 0, tzinfo=DUB))
    assert wake == datetime(2026, 9, 4, 15, 0, tzinfo=DUB) and page in POOL_LISTS["air"]
    regen, wake2, page2 = ts.next_regen(120, datetime(2026, 9, 4, 8, 0, tzinfo=DUB))
    assert (regen, wake2, page2) == (datetime(2026, 9, 4, 8, 58, tzinfo=DUB), datetime(2026, 9, 4, 9, 0, tzinfo=DUB), seq[0])
    assert ts.pages() == set(pool) | set(POOL_LISTS["air"])
    assert ts.describe()["type"] == "times" and ts.describe()["times"][0] == {"time": "09:00:00", "pool": "co2"}


def test_times_schedule_rejects_unknown_pools_and_bad_times():
    with pytest.raises(ValueError, match="names pools \\['zz'\\]"):
        TimesSchedule([("09:00:00", "zz")], POOLS, DUB)
    with pytest.raises(ValueError, match="not a valid time"):
        TimesSchedule([("9:00", "co2")], POOLS, DUB)
    with pytest.raises(ValueError):
        TimesSchedule([], POOLS, DUB)


def test_interval_schedule_visits_pools_in_order_each_on_its_own_count():
    it = IntervalSchedule(300, POOLS, DUB, order=["co2", "air", "day"])
    block = BLOCK // 300
    slots = list(range(28 * block, 28 * block + 12))          # inside one block
    names = [it.order[s % 3] for s in slots]
    assert names == ["co2", "air", "day"] * 4
    pages = [it.page_for_slot(s) for s in slots]
    for name, pool in POOL_LISTS.items():
        seen = [p for p, n in zip(pages, names) if n == name]
        start = pool.index(seen[0])
        assert seen == [pool[(start + k) % len(pool)] for k in range(len(seen))], name
    assert it.pages() == POOLS.pages()
    assert it.describe()["order"] == ["co2", "air", "day"] and it.describe()["type"] == "interval"


def test_interval_schedule_wake_and_regen_land_on_slot_boundaries():
    it = IntervalSchedule(300, POOLS, DUB)
    now = datetime(2026, 9, 4, 10, 2, 30, tzinfo=DUB)
    wake, page = it.next_wake(now)
    assert wake == datetime(2026, 9, 4, 10, 5, tzinfo=DUB) and page in it.pages()
    assert it.next_wake(datetime(2026, 9, 4, 10, 5, tzinfo=DUB))[0] == datetime(2026, 9, 4, 10, 10, tzinfo=DUB)
    regen, wake2, page2 = it.next_regen(60, now)
    assert (regen, wake2, page2) == (datetime(2026, 9, 4, 10, 4, tzinfo=DUB), wake, page)
    regen3, wake3, _ = it.next_regen(60, datetime(2026, 9, 4, 10, 4, tzinfo=DUB))
    assert wake3 == datetime(2026, 9, 4, 10, 10, tzinfo=DUB) and regen3 == datetime(2026, 9, 4, 10, 9, tzinfo=DUB)


def test_interval_schedule_order_can_leave_a_pool_out_and_is_checked():
    it = IntervalSchedule(300, POOLS, DUB, order=["co2"])
    assert it.pages() == set(POOL_LISTS["co2"])
    with pytest.raises(ValueError, match="names pools"):
        IntervalSchedule(300, POOLS, DUB, order=["nope"])
    with pytest.raises(ValueError, match="divide a day"):
        IntervalSchedule(7, POOLS, DUB)
