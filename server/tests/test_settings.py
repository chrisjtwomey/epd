"""Typed core settings in epd_server.config (server / image / mqtt / schedule)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from epd_server.config import (
    ConfigError,
    ImageSettings,
    load_core_config,
    load_yaml,
    parse_image,
    parse_mqtt,
    parse_server,
)

SCHEDULE = {"09:00:00": "today.png"}


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith(("SERVER_", "IMAGE_", "MQTT_", "DISPLAY_")) or key == "DEBUG":
            monkeypatch.delenv(key, raising=False)


# ---------- load_core_config: defaults ----------

def test_defaults_with_only_a_schedule():
    cfg = load_core_config({}, default_schedule=SCHEDULE)
    assert cfg.server.port == 8080
    assert cfg.server.regen_lead_seconds == 120
    assert cfg.server.display_schedule == [("09:00:00", "today.png")]
    assert cfg.server.debug is False
    assert cfg.server.timezone == datetime.now().astimezone().tzinfo
    assert (cfg.image.width, cfg.image.height) == (825, 1200)
    assert (cfg.image.inner_width, cfg.image.inner_height) == (825, 1200)
    assert (cfg.image.inner_align_x, cfg.image.inner_align_y) == ("center", "center")
    assert cfg.mqtt.enabled is False
    assert (cfg.mqtt.host, cfg.mqtt.port, cfg.mqtt.topic) == ("localhost", 1883, "mqtt/epd-client")


def test_project_can_change_every_default():
    cfg = load_core_config(
        {}, default_schedule={"07:00:00": "a.png"}, default_port=9000,
        default_regen_lead_seconds=30, default_width=600, default_height=448,
        default_mqtt_topic="mqtt/x",
    )
    assert cfg.server.port == 9000 and cfg.server.regen_lead_seconds == 30
    assert cfg.server.display_schedule == [("07:00:00", "a.png")]
    assert (cfg.image.width, cfg.image.height) == (600, 448)
    assert cfg.mqtt.topic == "mqtt/x"


def test_schedule_is_required_when_no_default():
    with pytest.raises(ConfigError, match="display_schedule is required"):
        load_core_config({})


# ---------- parse_server ----------

def test_schedule_is_sorted_and_values_stripped():
    # Keys are validated as-is (a padded time is an error, as before);
    # the image filenames are stripped.
    s = parse_server({"display_schedule": {"21:00:00": " b.png ", "09:00:00": "a.png"}})
    assert s.display_schedule == [("09:00:00", "a.png"), ("21:00:00", "b.png")]


def test_schedule_key_is_not_stripped_before_validation():
    with pytest.raises(ConfigError, match="' 21:00:00' is not a valid time"):
        parse_server({"display_schedule": {" 21:00:00": "b.png"}})


@pytest.mark.parametrize("bad", [[], {}, "09:00:00", 5])
def test_schedule_must_be_a_non_empty_mapping(bad):
    with pytest.raises(ConfigError, match="non-empty mapping"):
        parse_server({"display_schedule": bad})


def test_schedule_rejects_malformed_time():
    with pytest.raises(ConfigError, match="'9:00' is not a valid time"):
        parse_server({"display_schedule": {"9:00": "a.png"}})


def test_timezone_valid_and_invalid():
    s = parse_server({"display_schedule": SCHEDULE, "server": {"timezone": "Europe/Dublin"}})
    assert s.timezone == ZoneInfo("Europe/Dublin")
    with pytest.raises(ConfigError, match="not a valid IANA zone"):
        parse_server({"display_schedule": SCHEDULE, "server": {"timezone": "Mars/Olympus"}})


@pytest.mark.parametrize("bad", [-1, 1.5, "120", True])
def test_regen_lead_must_be_non_negative_int(bad):
    with pytest.raises(ConfigError, match="regen_lead_seconds"):
        parse_server({"display_schedule": SCHEDULE, "server": {"regen_lead_seconds": bad}})


@pytest.mark.parametrize("bad", [0, -8080, 70000, True, "8080"])
def test_port_must_be_a_valid_tcp_port(bad):
    with pytest.raises(ConfigError, match="server.port"):
        parse_server({"display_schedule": SCHEDULE, "server": {"port": bad}})


def test_env_overrides_server_port(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "9090")
    assert parse_server({"display_schedule": SCHEDULE}).port == 9090


def test_debug_is_top_level(monkeypatch):
    assert parse_server({"display_schedule": SCHEDULE, "debug": True}).debug is True
    monkeypatch.setenv("DEBUG", "true")
    assert parse_server({"display_schedule": SCHEDULE}).debug is True


# ---------- parse_image ----------

def test_inner_defaults_to_outer_and_page_kwargs_shape():
    img = parse_image({"image": {"width": 800, "height": 600}})
    assert img == ImageSettings(800, 600, 800, 600, "center", "center")
    assert img.page_kwargs() == dict(width=800, height=600, inner_width=800, inner_height=600,
                                     inner_align_x="center", inner_align_y="center")


def test_alignment_is_normalised():
    img = parse_image({"image": {"innerAlignX": " Left ", "innerAlignY": "BOTTOM"}})
    assert (img.inner_align_x, img.inner_align_y) == ("left", "bottom")


@pytest.mark.parametrize("key,value", [
    ("innerAlignX", "middle"), ("innerAlignX", "top"),
    ("innerAlignY", "left"), ("innerAlignY", "middle"),
])
def test_rejects_invalid_alignment(key, value):
    with pytest.raises(ConfigError, match=f"image.{key} must be one of"):
        parse_image({"image": {key: value}})


@pytest.mark.parametrize("key", ["width", "height", "innerWidth", "innerHeight"])
@pytest.mark.parametrize("bad", [0, -1, 1.5, "825", True])
def test_dimensions_must_be_positive_ints(key, bad):
    with pytest.raises(ConfigError, match=f"image.{key} must be a positive integer"):
        parse_image({"image": {key: bad}})


def test_inner_cannot_exceed_outer():
    with pytest.raises(ConfigError, match="innerWidth \\(900\\) cannot be greater than image.width \\(825\\)"):
        parse_image({"image": {"innerWidth": 900}})
    with pytest.raises(ConfigError, match="innerHeight"):
        parse_image({"image": {"innerHeight": 1300}})


# ---------- parse_mqtt ----------

def test_mqtt_env_override_coerces_types(monkeypatch):
    monkeypatch.setenv("MQTT_ENABLED", "yes")
    monkeypatch.setenv("MQTT_PORT", "1884")
    m = parse_mqtt({"mqtt": {"host": "broker"}})
    assert (m.enabled, m.host, m.port, m.topic) == (True, "broker", 1884, "mqtt/epd-client")


def test_mqtt_port_validated():
    with pytest.raises(ConfigError, match="mqtt.port"):
        parse_mqtt({"mqtt": {"port": 0}})


# ---------- load_yaml ----------

def test_load_yaml_reads_mapping_and_treats_empty_as_empty_dict(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("server:\n  port: 1234\n")
    assert load_yaml(f) == {"server": {"port": 1234}}
    f.write_text("")
    assert load_yaml(f) == {}


def test_load_yaml_rejects_non_mapping(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError, match="top level must be a mapping"):
        load_yaml(f)
