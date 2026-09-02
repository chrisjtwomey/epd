"""DataSource helpers in epd_server.source."""
import pytest

from epd_server.source import CompositeSource, DataSource, StaticSource


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
