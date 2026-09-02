"""Plugin registry in epd_server.registry."""
import pytest

from epd_server.registry import Registry


def make():
    reg = Registry("widget")

    @reg.register("plain")
    class Plain:
        def __init__(self, *, apikey=None, location=None):
            self.apikey = apikey
            self.location = location

    @reg.register("greedy")
    class Greedy:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    return reg, Plain, Greedy


def test_register_and_names():
    reg, _, _ = make()
    assert set(reg.names()) == {"plain", "greedy"}
    assert "plain" in reg
    assert "nope" not in reg
    assert len(reg) == 2


def test_create_forwards_only_declared_kwargs():
    reg, Plain, _ = make()
    obj = reg.create("plain", apikey="k", location="Dublin", num_hours=9, metric=True)
    assert isinstance(obj, Plain)
    assert obj.apikey == "k" and obj.location == "Dublin"


def test_create_passes_everything_to_var_kwargs_constructor():
    reg, _, Greedy = make()
    obj = reg.create("greedy", apikey="k", num_hours=9)
    assert isinstance(obj, Greedy)
    assert obj.kwargs == {"apikey": "k", "num_hours": 9}


def test_create_unknown_name_lists_supported():
    reg, _, _ = make()
    with pytest.raises(ValueError, match=r"Unknown widget 'nope'. Supported: greedy, plain"):
        reg.create("nope")


def test_registries_are_independent():
    a, b = Registry("a"), Registry("b")
    a.add("x", object)
    assert "x" in a and "x" not in b
