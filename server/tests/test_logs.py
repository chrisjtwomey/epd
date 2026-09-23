"""The boards' log lines, kept and read back."""
import pytest

from epd_server.logs import LEVELS, LogStore, level_of


@pytest.fixture
def clock():
    return [1000.0]


@pytest.fixture
def store(clock):
    return LogStore(":memory:", now=lambda: clock[0])


def test_a_line_states_its_level_with_or_without_a_stamp():
    assert LEVELS[level_of("WARNING - low battery")] == "WARNING"
    assert LEVELS[level_of("2026-09-23T09:30:00+01:00 - ERROR - fetch failed")] == "ERROR"
    assert level_of("a line with no level") is None
    assert level_of("INFORMATION - not a level") is None


def test_lines_come_back_oldest_first_with_the_board_and_arrival(store, clock):
    store.add("canary-dock", "INFO - one")
    clock[0] = 1005.0
    store.add("canary-head", "WARNING - two")
    assert store.lines() == [
        {"id": 1, "board": "canary-dock", "received": 1000.0, "level": "INFO", "text": "INFO - one"},
        {"id": 2, "board": "canary-head", "received": 1005.0, "level": "WARNING", "text": "WARNING - two"},
    ]


def test_after_follows_new_lines_and_before_reads_back(store):
    for n in range(10):
        store.add("b", f"INFO - {n}")
    assert [line["id"] for line in store.lines(after=7)] == [8, 9, 10]
    assert [line["id"] for line in store.lines(before=4)] == [1, 2, 3]
    assert [line["id"] for line in store.lines(limit=3)] == [8, 9, 10], "the newest, oldest first"
    assert [line["id"] for line in store.lines(after=2, limit=2)] == [3, 4]
    assert [line["id"] for line in store.lines(before=9, limit=2)] == [7, 8]


def test_filters_by_board_level_and_text(store):
    store.add("canary-dock", "DEBUG - noisy")
    store.add("canary-dock", "ERROR - fetch failed: 50% of 1_000")
    store.add("canary-head", "NOTICE - boot")
    store.add("canary-head", "a line with no level")
    assert [line["text"] for line in store.lines(board="canary-head")] == \
        ["NOTICE - boot", "a line with no level"]
    assert [line["text"] for line in store.lines(level=LEVELS.index("NOTICE"))] == \
        ["ERROR - fetch failed: 50% of 1_000", "NOTICE - boot"]
    assert [line["text"] for line in store.lines(contains="50%")] == \
        ["ERROR - fetch failed: 50% of 1_000"]
    assert store.lines(contains="%") == store.lines(contains="50%"), "% is a character, not a wildcard"
    assert store.lines(contains="1_0") and not store.lines(contains="1x0")
    assert store.boards() == ["canary-dock", "canary-head"]


def test_old_lines_go_as_new_ones_arrive(clock, monkeypatch):
    monkeypatch.setattr(LogStore, "PRUNE_EVERY", 2)
    store = LogStore(":memory:", keep_days=1, now=lambda: clock[0])
    store.add("b", "INFO - old")
    clock[0] += 2 * 86400
    store.add("b", "INFO - new")
    assert [line["text"] for line in store.lines()] == ["INFO - new"]
    assert store.count() == 1


def test_the_same_line_at_the_same_moment_is_one_line(store):
    assert store.add("b", "INFO - once") == 1
    assert store.add("b", "INFO - once") is None
    assert store.add("other", "INFO - once") is not None
    assert store.count() == 2


def test_an_empty_store(store):
    assert store.lines() == [] and store.boards() == [] and store.count() == 0
