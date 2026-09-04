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
    validate_time_list("display_schedule", ["00:00:00", "09:30:00", "23:59:59"])


@pytest.mark.parametrize("bad", ["9:00", "09:00", "25:00:00", "09:60:00", "nine", ""])
def test_validate_time_list_rejects_malformed(bad):
    with pytest.raises(ValueError, match="display_schedule"):
        validate_time_list("display_schedule", ["09:00:00", bad])


# ---------- schedule objects ----------

from epd_server.scheduling import PoolSchedule, TimeListSchedule  # noqa: E402

DUB = ZoneInfo("Europe/Dublin")
POOLS = {"co2": ["breathe.png", "co2-trace.png", "co2-delta.png"],
         "air": ["air.png", "air-trace.png"],
         "day": ["day.png"]}


def test_time_list_object_matches_the_functions():
    sched = [("09:00:00", "a.png"), ("15:00:00", "b.png")]
    obj = TimeListSchedule(sched, DUB)
    now = datetime(2026, 9, 4, 10, 0, tzinfo=DUB)
    assert obj.next_wake(now) == next_wake(sched, DUB, now)
    assert obj.next_regen(120, now) == next_regen(sched, DUB, 120, now)
    assert obj.pages() == {"a.png", "b.png"}
    assert obj.describe() == [{"time": "09:00:00", "page": "a.png"}, {"time": "15:00:00", "page": "b.png"}]
    with pytest.raises(ValueError):
        TimeListSchedule([], DUB)


def test_pool_schedule_visits_pools_round_robin_and_each_pool_on_its_own_count():
    ps = PoolSchedule(300, POOLS, DUB, reshuffle_hours=3, seed=1)
    block = 3 * 3600 // 300              # slots per reshuffle block
    slots = list(range(28 * block, 28 * block + 12))   # inside one block
    pools = [ps.names[s % 3] for s in slots]
    assert pools == ["co2", "air", "day"] * 4
    pages = [ps.page_for_slot(s) for s in slots]
    for name in POOLS:
        seen = [p for p, n in zip(pages, pools) if n == name]
        pool = POOLS[name]
        start = pool.index(seen[0])
        assert seen == [pool[(start + k) % len(pool)] for k in range(len(seen))], name
    assert ps.pages() == set(sum(POOLS.values(), []))
    assert ps.describe()[0] == {"pool": "co2", "pages": POOLS["co2"]}


def test_pool_schedule_starts_change_between_blocks_but_not_between_processes():
    ps = PoolSchedule(300, POOLS, DUB, reshuffle_hours=3, seed=7)
    same = PoolSchedule(300, POOLS, DUB, reshuffle_hours=3, seed=7)
    assert [ps.page_for_slot(s) for s in range(5000)] == [same.page_for_slot(s) for s in range(5000)]
    # the co2 pool's phase within a block is constant; across blocks it is not always
    block = 3 * 3600 // 300     # slots per block
    phases = []
    for b in range(40):
        first = next(s for s in range(b * block, (b + 1) * block) if s % 3 == 0)
        phases.append((POOLS["co2"].index(ps.page_for_slot(first)) - first // 3) % 3)
    assert len(set(phases)) > 1
    other = PoolSchedule(300, POOLS, DUB, reshuffle_hours=3, seed=8)
    assert [ps.page_for_slot(s) for s in range(300)] != [other.page_for_slot(s) for s in range(300)]


def test_pool_schedule_wake_and_regen_land_on_slot_boundaries():
    ps = PoolSchedule(300, POOLS, DUB, seed=1)
    now = datetime(2026, 9, 4, 10, 2, 30, tzinfo=DUB)
    wake, page = ps.next_wake(now)
    assert wake == datetime(2026, 9, 4, 10, 5, tzinfo=DUB) and page in ps.pages()
    assert ps.next_wake(datetime(2026, 9, 4, 10, 5, tzinfo=DUB))[0] == datetime(2026, 9, 4, 10, 10, tzinfo=DUB)
    regen, wake2, page2 = ps.next_regen(60, now)
    assert (regen, wake2, page2) == (datetime(2026, 9, 4, 10, 4, tzinfo=DUB), wake, page)
    # at the regen moment the following slot is chosen, as the time list does
    regen3, wake3, _ = ps.next_regen(60, datetime(2026, 9, 4, 10, 4, tzinfo=DUB))
    assert wake3 == datetime(2026, 9, 4, 10, 10, tzinfo=DUB) and regen3 == datetime(2026, 9, 4, 10, 9, tzinfo=DUB)


@pytest.mark.parametrize("every, pools, hours", [
    (7, POOLS, 3), (0, POOLS, 3), (300, {}, 3), (300, {"x": []}, 3), (300, POOLS, 0),
])
def test_pool_schedule_rejects_bad_shapes(every, pools, hours):
    with pytest.raises(ValueError):
        PoolSchedule(every, pools, DUB, reshuffle_hours=hours)
