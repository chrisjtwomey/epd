"""Env-override resolver in epd_server.config."""
import pytest

from epd_server.config import (
    _coerce_env,
    _env_name,
    _resolve,
    get_prop,
    get_prop_by_keys,
)


CONFIG = {
    "server": {
        "port": 8080,
        "timezone": "Europe/Dublin",
        "refresh_times": ["09:00:00"],
    },
    "weather": {"service": "accuweather", "apikey": "yaml-key", "metric": True},
    "mqtt": {"enabled": False, "port": 1883},
    "location": "Cork",
}


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith(("WEATHER_", "SERVER_", "MQTT_", "NEW_")) or key == "LOCATION":
            monkeypatch.delenv(key, raising=False)


# ---------- _env_name ----------

def test_env_name_joins_with_underscore_and_uppercases():
    assert _env_name(("weather", "apikey")) == "WEATHER_APIKEY"
    assert _env_name(("server", "refresh_times")) == "SERVER_REFRESH_TIMES"
    assert _env_name(("location",)) == "LOCATION"


# ---------- _coerce_env ----------

@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("True", True),
    ("yes", True), ("on", True), ("ON", True),
    ("0", False), ("false", False), ("no", False), ("off", False),
    ("", False), ("anything-else", False),
])
def test_coerce_env_bool(raw, expected):
    assert _coerce_env(raw, True) is expected


def test_coerce_env_int():
    assert _coerce_env("9090", 8080) == 9090


def test_coerce_env_float():
    assert _coerce_env("3.14", 1.0) == pytest.approx(3.14)


def test_coerce_env_list_csv():
    assert _coerce_env("07:00:00, 12:00:00 ,18:00:00", ["x"]) == [
        "07:00:00", "12:00:00", "18:00:00"
    ]


def test_coerce_env_list_strips_empty_entries():
    assert _coerce_env("a,,b,", ["x"]) == ["a", "b"]


def test_coerce_env_str_passthrough():
    assert _coerce_env("hello", "default") == "hello"


def test_coerce_env_bool_before_int_isinstance_order():
    # bool is a subclass of int in Python; the resolver must check bool first.
    assert _coerce_env("true", True) is True
    assert _coerce_env("0", True) is False


# ---------- _resolve precedence ----------

def _missing():
    raise KeyError()


def test_resolve_returns_yaml_when_no_env():
    val = _resolve(("weather", "apikey"),
                   lambda: CONFIG["weather"]["apikey"], None, True)
    assert val == "yaml-key"


def test_resolve_returns_default_when_yaml_missing():
    assert _resolve(("absent",), _missing, "fallback", False) == "fallback"


def test_resolve_raises_when_required_and_missing():
    with pytest.raises(KeyError):
        _resolve(("nope",), _missing, None, True)


def test_resolve_env_overrides_yaml(monkeypatch):
    monkeypatch.setenv("WEATHER_APIKEY", "from-env")
    val = _resolve(("weather", "apikey"),
                   lambda: CONFIG["weather"]["apikey"], None, True)
    assert val == "from-env"


def test_resolve_env_overrides_default(monkeypatch):
    monkeypatch.setenv("NEW_FIELD", "from-env")
    assert _resolve(("new", "field"), _missing, "default", False) == "from-env"


def test_resolve_env_coerces_to_yaml_type(monkeypatch):
    """Bool/int coercion uses yaml value as the type reference."""
    monkeypatch.setenv("MQTT_ENABLED", "true")
    val = _resolve(("mqtt", "enabled"),
                   lambda: CONFIG["mqtt"]["enabled"], False, True)
    assert val is True


# ---------- get_prop / get_prop_by_keys integration ----------

def test_get_prop_by_keys_yaml_path():
    assert get_prop_by_keys(CONFIG, "server", "port", default=8080) == 8080


def test_get_prop_by_keys_env_override(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "9090")
    assert get_prop_by_keys(CONFIG, "server", "port", default=8080) == 9090


def test_get_prop_by_keys_list_env_override(monkeypatch):
    monkeypatch.setenv("SERVER_REFRESH_TIMES", "07:00:00,12:00:00,18:00:00")
    val = get_prop_by_keys(CONFIG, "server", "refresh_times")
    assert val == ["07:00:00", "12:00:00", "18:00:00"]


def test_get_prop_top_level():
    assert get_prop(CONFIG, "location") == "Cork"


def test_get_prop_env_override(monkeypatch):
    monkeypatch.setenv("LOCATION", "Galway")
    assert get_prop(CONFIG, "location") == "Galway"


def test_get_prop_missing_required_raises():
    with pytest.raises(KeyError):
        get_prop({}, "absent")


def test_get_prop_missing_with_default():
    assert get_prop({}, "absent", default="x", required=False) == "x"
