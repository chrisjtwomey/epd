"""LogsQuery: the lines a /logs route asks for."""
from zoneinfo import ZoneInfo

import pytest

from epd_server.logs import MAX_LINES, LogsQuery, LogStore


@pytest.fixture
def store():
    clock = [1_790_000_000.0]

    def now():
        clock[0] += 1
        return clock[0]

    s = LogStore(":memory:", now=now)
    for n in range(5):
        s.add("canary-dock", f"INFO - reading {n}")
    s.add("canary-display", "WARNING - fetch took 3 tries")
    s.add("canary-dock", "ERROR - POST failed")
    yield s
    s.close()


@pytest.fixture
def query(store):
    return LogsQuery(store, ZoneInfo("Europe/Dublin"))


def test_the_newest_lines_every_board_and_the_zone(query):
    answer = query.answer({"limit": "3"})
    assert [line["text"] for line in answer["lines"]] == \
        ["INFO - reading 4", "WARNING - fetch took 3 tries", "ERROR - POST failed"]
    assert answer["boards"] == ["canary-display", "canary-dock"]
    assert answer["tz"] == "Europe/Dublin"


def test_paging_forward_and_back(query):
    assert [line["id"] for line in query.answer({"after": "5"})["lines"]] == [6, 7]
    assert [line["id"] for line in query.answer({"before": "3"})["lines"]] == [1, 2]


def test_filters(query):
    assert [line["board"] for line in query.answer({"board": "canary-display"})["lines"]] == ["canary-display"]
    assert [line["level"] for line in query.answer({"level": "WARNING"})["lines"]] == ["WARNING", "ERROR"]
    assert [line["text"] for line in query.answer({"q": "POST"})["lines"]] == ["ERROR - POST failed"]
    assert query.answer({"board": "", "level": "", "q": ""})["lines"] == query.answer({})["lines"]


def test_an_answer_is_capped(query, monkeypatch):
    asked = {}
    monkeypatch.setattr(query.store, "lines", lambda **kw: asked.update(kw) or [])
    query.answer({"limit": "100000"})
    assert asked["limit"] == MAX_LINES


@pytest.mark.parametrize("args", [{"after": "x"}, {"limit": "1.5"}, {"level": "LOUD"}])
def test_a_bad_argument_is_refused(query, args):
    with pytest.raises(ValueError):
        query.answer(args)
