"""DataSource helpers in epd_server.source."""
import pytest

from epd_server.source import CompositeSource, DataSource, IngestSource, StaticSource
from epd_server.store import ReadingsStore


class Counting(DataSource):
    """Records fetch and invalidate calls."""

    def __init__(self, **values):
        self.values = values
        self.fetched = []
        self.invalidated = 0

    def datasets(self):
        def make(name):
            def fetch():
                self.fetched.append(name)
                return self.values[name]
            return fetch
        return {name: make(name) for name in self.values}

    def invalidate(self):
        self.invalidated += 1


def test_datasource_is_abstract():
    with pytest.raises(TypeError):
        DataSource()  # type: ignore[abstract]


def test_default_invalidate_is_a_noop():
    class Minimal(DataSource):
        def datasets(self):
            return {}
    Minimal().invalidate()


def test_static_source_returns_fixed_values_lazily():
    src = StaticSource(map_url="http://x/map.png", n=3)
    ds = src.datasets()
    assert set(ds) == {"map_url", "n"}
    assert ds["map_url"]() == "http://x/map.png"
    assert ds["n"]() == 3


def test_static_source_closures_do_not_share_state():
    ds = StaticSource(a=1, b=2).datasets()
    assert (ds["a"](), ds["b"]()) == (1, 2)


def test_composite_merges_datasets_and_fans_out_invalidate():
    a, b = Counting(x=1), Counting(y=2)
    comp = CompositeSource(StaticSource(z=3), a, b)
    ds = comp.datasets()
    assert set(ds) == {"x", "y", "z"}
    assert ds["x"]() == 1 and ds["y"]() == 2 and ds["z"]() == 3
    comp.invalidate()
    assert a.invalidated == 1 and b.invalidated == 1


def test_composite_rejects_colliding_names():
    with pytest.raises(ValueError, match="'x' is provided by both Counting and StaticSource"):
        CompositeSource(Counting(x=1), StaticSource(x=2)).datasets()


def test_ingest_source_serves_the_newest_and_each_window(tmp_path):
    store = ReadingsStore(tmp_path / "r.db")
    now = 10 * 86400
    for ts in (now - 80 * 3600, now - 30 * 3600, now - 3600, now - 60):
        store.add({"ts": ts, "device": "a"})
    ds = IngestSource(store, hours=(24, 72), now=lambda: now).datasets()
    assert set(ds) == {"latest", "history_24h", "history_72h"}
    assert ds["latest"]()["ts"] == now - 60
    assert [d["ts"] for d in ds["history_24h"]()] == [now - 3600, now - 60]
    assert [d["ts"] for d in ds["history_72h"]()] == [now - 30 * 3600, now - 3600, now - 60]


def test_ingest_source_before_the_first_document(tmp_path):
    ds = IngestSource(ReadingsStore(tmp_path / "r.db")).datasets()
    assert ds["latest"]() is None
    assert ds["history_24h"]() == []


def test_ingest_source_can_follow_one_board(tmp_path):
    store = ReadingsStore(tmp_path / "r.db")
    store.add({"ts": 1, "device": "a"})
    store.add({"ts": 2, "device": "b"})
    ds = IngestSource(store, device="a", now=lambda: 3).datasets()
    assert ds["latest"]()["device"] == "a"
    assert [d["device"] for d in ds["history_24h"]()] == ["a"]
