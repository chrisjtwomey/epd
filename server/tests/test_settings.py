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

from epd_server.scheduling import TimeRangesSchedule, TimesSchedule  # noqa: E402

DISPLAY = {"pools": {"today": ["today.png"]}, "schedule": {"type": "times", "09:00:00": "today"}}


def display(pools: dict, **schedule) -> dict:
    return {"display": {"pools": pools, "schedule": schedule}}


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith(("SERVER_", "IMAGE_", "MQTT_", "DISPLAY_", "FIRMWARE_", "CLIENT_")) \
                or key == "DEBUG":
            monkeypatch.delenv(key, raising=False)


# ---------- load_core_config: defaults ----------

def test_defaults_with_only_a_display():
    cfg = load_core_config({}, default_display=DISPLAY)
    assert cfg.server.port == 8080
    assert cfg.server.regen_lead_seconds == 120
    assert isinstance(cfg.server.schedule, TimesSchedule)
    assert list(cfg.server.schedule) == [("09:00:00", "today")]
    assert cfg.server.schedule.pages() == {"today.png"}
    assert cfg.server.debug is False
    assert cfg.server.timezone == datetime.now().astimezone().tzinfo
    assert (cfg.image.width, cfg.image.height) == (825, 1200)
    assert (cfg.image.inner_width, cfg.image.inner_height) == (825, 1200)
    assert (cfg.image.inner_align_x, cfg.image.inner_align_y) == ("center", "center")
    assert cfg.mqtt.enabled is False
    assert (cfg.mqtt.host, cfg.mqtt.port, cfg.mqtt.prefix) == ("localhost", 1883, "mqtt/epd")


def test_project_can_change_every_default():
    cfg = load_core_config(
        {}, default_display=display({"a": ["a.png"]}, type="times", **{"07:00:00": "a"})["display"],
        default_port=9000, default_regen_lead_seconds=30, default_width=600, default_height=448,
        default_mqtt_prefix="mqtt/x",
    )
    assert cfg.server.port == 9000 and cfg.server.regen_lead_seconds == 30
    assert isinstance(cfg.server.schedule, TimesSchedule)   # the block said type: times
    assert list(cfg.server.schedule) == [("07:00:00", "a")]
    assert (cfg.image.width, cfg.image.height) == (600, 448)
    assert cfg.mqtt.prefix == "mqtt/x"


def test_display_is_required_when_no_default():
    with pytest.raises(ConfigError, match="display is required"):
        load_core_config({})


def test_times_schedule_is_sorted_and_pool_names_stripped():
    s = parse_server(display({"a": ["a.png"], "b": [" b.png "]}, type="times",
                             **{"21:00:00": " b ", "09:00:00": "a"})).schedule
    assert isinstance(s, TimesSchedule)
    assert list(s) == [("09:00:00", "a"), ("21:00:00", "b")]
    assert s.pages() == {"a.png", "b.png"}


def test_times_key_is_not_stripped_before_validation():
    with pytest.raises(ConfigError, match="' 21:00:00' is not a valid time"):
        parse_server(display({"b": ["b.png"]}, type="times", **{" 21:00:00": "b"}))


def test_times_rejects_malformed_time():
    with pytest.raises(ConfigError, match="'9:00' is not a valid time"):
        parse_server(display({"a": ["a.png"]}, type="times", **{"9:00": "a"}))


def test_times_must_name_a_defined_pool():
    with pytest.raises(ConfigError, match="names pools \\['x'\\]"):
        parse_server(display({"a": ["a.png"]}, type="times", **{"09:00:00": "x"}))


def test_times_needs_at_least_one_entry():
    with pytest.raises(ConfigError, match="at least one"):
        parse_server(display({"a": ["a.png"]}, type="times"))


# ---------- parse_display: timeranges ----------

ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def every_day(ranges):
    return [{"days": ALL_DAYS, "ranges": ranges}]


EVERY_5_MIN = every_day([{"from": "00:00", "every": 300}])


def test_timeranges_visit_the_pools_in_order():
    week = [{"days": ["mon", "tue", "wed", "thu", "fri"],
             "ranges": [{"from": "07:00", "every": 300}, {"from": "23:00", "every": 0}]},
            {"days": ["sat", "sun"], "ranges": [{"from": "09:00", "every": 600}]}]
    raw = display({"co2": ["a.png", "b.png"], "day": "day.png"}, type="timeranges", week=week,
                  reshuffle_hours=2, order=["day", "co2"])
    s = parse_server(raw).schedule
    assert isinstance(s, TimeRangesSchedule)
    assert s.week.describe() == week
    assert s.order == ["day", "co2"] and s.pools.reshuffle_seconds == 7200
    assert s.pools.pools["day"] == ["day.png"]
    assert s.pages() == {"a.png", "b.png", "day.png"}


def test_timeranges_order_defaults_to_every_pool():
    s = parse_server(display({"x": ["x.png"], "y": ["y.png"]}, type="timeranges",
                             week=EVERY_5_MIN)).schedule
    assert isinstance(s, TimeRangesSchedule)
    assert s.order == ["x", "y"]


@pytest.mark.parametrize("bad, match", [
    ({"pools": {}, "schedule": {"type": "times", "09:00:00": "a"}}, "display.pools must be"),
    ({"pools": {"a": []}, "schedule": {"type": "times", "09:00:00": "a"}}, "non-empty list"),
    ({"pools": {"a": ["a.png"]}}, "display.schedule must be"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "daily"}}, "type must be times or timeranges"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "interval", "every": 300}}, "type must be times or timeranges"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "timeranges"}}, "^display.schedule.week must be a list"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "timeranges",
                                              "week": every_day([{"from": "07:00", "every": 7}])}},
     "^display.schedule.week\\[0\\].ranges every must be 0"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "timeranges",
                                              "week": every_day([{"from": "07:00", "every": 0}])}},
     "^display.schedule.week has no range with an interval"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "timeranges", "ranges": EVERY_5_MIN}}, "takes week, order"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "timeranges", "week": EVERY_5_MIN, "every": 300}}, "takes week, order"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "timeranges", "week": EVERY_5_MIN, "order": ["zz"]}}, "names pools \\['zz'\\]"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "timeranges", "week": EVERY_5_MIN, "reshuffle_hours": 0}}, "positive number"),
    ({"pools": {"a": ["a.png"]}, "schedule": {"type": "times", "09:00:00": "a"}, "extra": 1}, "display takes pools and schedule"),
    ("nope", "display needs pools and schedule"),
])
def test_display_rejects_bad_shapes(bad, match):
    with pytest.raises(ConfigError, match=match):
        parse_server({"display": bad})


def test_timezone_valid_and_invalid():
    s = parse_server({"display": DISPLAY, "server": {"timezone": "Europe/Dublin"}})
    assert s.timezone == ZoneInfo("Europe/Dublin")
    with pytest.raises(ConfigError, match="not a valid IANA zone"):
        parse_server({"display": DISPLAY, "server": {"timezone": "Mars/Olympus"}})


@pytest.mark.parametrize("bad", [-1, 1.5, "120", True])
def test_regen_lead_must_be_non_negative_int(bad):
    with pytest.raises(ConfigError, match="regen_lead_seconds"):
        parse_server({"display": DISPLAY, "server": {"regen_lead_seconds": bad}})


@pytest.mark.parametrize("bad", [0, -8080, 70000, True, "8080"])
def test_port_must_be_a_valid_tcp_port(bad):
    with pytest.raises(ConfigError, match="server.port"):
        parse_server({"display": DISPLAY, "server": {"port": bad}})


def test_https_port_defaults_on_and_0_turns_it_off():
    assert load_core_config({}, default_display=DISPLAY).server.https_port == 8443
    assert parse_server({"server": {"https_port": 0}}, default_display=DISPLAY).https_port == 0
    assert load_core_config({}, default_display=DISPLAY,
                            default_https_port=9443).server.https_port == 9443


@pytest.mark.parametrize("bad", [-1, 65536, "8443", True])
def test_https_port_must_be_a_port_or_0(bad):
    with pytest.raises(ConfigError, match="server.https_port must be a port, or 0 for none"):
        parse_server({"server": {"https_port": bad}}, default_display=DISPLAY)


def test_https_port_must_differ_from_the_port():
    with pytest.raises(ConfigError, match=r"server.https_port must differ from server.port \(8080\)"):
        parse_server({"server": {"port": 8080, "https_port": 8080}}, default_display=DISPLAY)


def test_env_overrides_server_port(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "9090")
    assert parse_server({"display": DISPLAY}).port == 9090


def test_debug_is_top_level(monkeypatch):
    assert parse_server({"display": DISPLAY, "debug": True}).debug is True
    monkeypatch.setenv("DEBUG", "true")
    assert parse_server({"display": DISPLAY}).debug is True


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
    assert (m.enabled, m.host, m.port, m.prefix) == (True, "broker", 1884, "mqtt/epd")


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


# ---------- firmware ----------

from epd_server.config import FirmwareSettings, parse_firmware  # noqa: E402


def firmware_cfg(**firmware):
    return {"client": {"firmware": firmware}}


def test_firmware_is_off_by_default():
    fw = load_core_config({}, default_display=DISPLAY).firmware
    assert fw.enabled is False and fw.offer_dev_builds is False
    assert fw.dir == "firmware" and fw.product == ""


def test_firmware_block_is_read():
    fw = parse_firmware(firmware_cfg(enabled=True, dir="/srv/images",
                               product="my-display", offer_dev_builds=True))
    assert fw == FirmwareSettings(True, "/srv/images", "my-display", True)


def test_the_project_supplies_the_product_so_the_config_need_not():
    fw = parse_firmware(firmware_cfg(enabled=True), default_product="my-display")
    assert fw.product == "my-display"
    assert parse_firmware(firmware_cfg(enabled=True, product="other"),
                          default_product="my-display").product == "other"


def test_several_products_each_keep_their_images_in_a_subdirectory():
    fw = parse_firmware(firmware_cfg(enabled=True, dir="/srv/images",
                                     products=["my-display", "my-sensor"]))
    assert fw.product == "my-display" and fw.names() == ("my-display", "my-sensor")
    assert fw.dir_for("my-sensor") == "/srv/images/my-sensor"
    one = parse_firmware(firmware_cfg(enabled=True, dir="/srv/images", product="my-display"))
    assert one.names() == ("my-display",) and one.dir_for("my-display") == "/srv/images"


@pytest.mark.parametrize("products", ["my-display", ["my-display", ""], [3]])
def test_products_must_be_a_list_of_names(products):
    with pytest.raises(ConfigError, match="products must be a list"):
        parse_firmware(firmware_cfg(enabled=True, products=products))


def test_an_enabled_block_without_a_product_is_refused():
    with pytest.raises(ConfigError, match="client.firmware.product is required"):
        parse_firmware(firmware_cfg(enabled=True))
    assert parse_firmware(firmware_cfg(enabled=False)).product == ""


def test_firmware_env_overrides_coerce_types(monkeypatch):
    monkeypatch.setenv("CLIENT_FIRMWARE_ENABLED", "true")
    monkeypatch.setenv("CLIENT_FIRMWARE_OFFER_DEV_BUILDS", "true")
    monkeypatch.setenv("CLIENT_FIRMWARE_DIR", "/tmp/fw")
    fw = parse_firmware(firmware_cfg(product="my-display"))
    assert fw.enabled is True and fw.offer_dev_builds is True and fw.dir == "/tmp/fw"


def test_firmware_source_defaults_and_product_from_the_repo_name():
    fw = parse_firmware(firmware_cfg(enabled=True, source={"github": "owner/my-display"}))
    assert fw.product == "my-display"
    assert fw.source is not None
    assert fw.source.asset == "firmware.bin" and fw.source.poll_seconds == 3600
    assert fw.source.token == ""


def test_no_source_block_means_images_are_placed_by_hand():
    assert parse_firmware(firmware_cfg(enabled=True, product="cal")).source is None


@pytest.mark.parametrize("source, match", [
    ({"github": "not-a-repo"}, "must be owner/repo"),
    ({"github": "a/b", "asset": " "}, "must name the release asset"),
    ({"github": "a/b", "poll_seconds": 0}, "poll_seconds must be a positive integer"),
])
def test_a_bad_source_block_is_refused(source, match):
    with pytest.raises(ConfigError, match=match):
        parse_firmware(firmware_cfg(enabled=True, source=source))


def test_the_token_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLIENT_FIRMWARE_SOURCE_TOKEN", "ghp_secret")
    fw = parse_firmware(firmware_cfg(enabled=True, source={"github": "a/b"}))
    assert fw.source is not None and fw.source.token == "ghp_secret"


def test_a_relative_firmware_dir_resolves_against_the_config_file(tmp_path):
    fw = parse_firmware(firmware_cfg(product="cal"), base_dir=str(tmp_path))
    assert fw.dir == str(tmp_path / "firmware")
    absolute = parse_firmware(firmware_cfg(dir="/srv/images"), base_dir=str(tmp_path))
    assert absolute.dir == "/srv/images"


# ---------- network ----------

from epd_server.config import MqttSettings, NetworkSettings, parse_network  # noqa: E402

MQTT_ON = MqttSettings(True, "mosquitto", 1883, "mqtt/epd")
MQTT_OFF = MqttSettings(False, "localhost", 1883, "mqtt/epd")


def network_cfg(wifi=None, **client):
    return {"client": {**client, **({"wifi": wifi} if wifi is not None else {})}}


def test_no_network_keys_is_a_server_that_still_runs():
    network = load_core_config({}, default_display=DISPLAY).network
    assert network == NetworkSettings()
    assert network.missing(MQTT_OFF) == ["client.server_url", "client.wifi.ssid",
                                         "client.wifi.password"]
    assert network.missing(MQTT_ON)[-1] == "client.mqtt_host"


def test_the_network_keys_are_read():
    network = parse_network(network_cfg(
        server_url="http://epd.local:8080/", mqtt_host="epd.local",
        wifi={"ssid": "Home", "password": "correct horse"}))
    assert network == NetworkSettings("http://epd.local:8080", "Home", "correct horse", "epd.local")
    assert network.missing(MQTT_ON) == []


def test_an_ssid_and_a_password_keep_their_spaces():
    network = parse_network(network_cfg(wifi={"ssid": " Home ", "password": " 8 chars "}))
    assert (network.wifi_ssid, network.wifi_password) == (" Home ", " 8 chars ")


def test_an_empty_password_is_not_set():
    assert parse_network(network_cfg(wifi={"password": ""})).missing(MQTT_OFF)[-1] == \
        "client.wifi.password"


def test_the_network_keys_come_from_the_environment_too(monkeypatch):
    monkeypatch.setenv("CLIENT_WIFI_PASSWORD", "from the env")
    monkeypatch.setenv("CLIENT_SERVER_URL", "http://10.0.0.2:8080")
    network = parse_network(network_cfg(wifi={"password": "from the file"}))
    assert (network.wifi_password, network.server_url) == ("from the env", "http://10.0.0.2:8080")


@pytest.mark.parametrize("url", [
    "https://epd.local",            # the boards speak plain HTTP
    "epd.local:8080",               # no scheme
    "http://",                      # no host
    "http://epd.local/epd",         # a path, which the dock would drop
    "http://epd.local/?page=1",     # a query
    "http://epd.local:99999",       # a port out of range
    "http://epd.local:0",
    "http://epd.local:port",
    "http://me@epd.local",          # a user
])
def test_a_server_url_must_be_an_http_host_and_port(url):
    with pytest.raises(ConfigError, match="client.server_url must be http://host"):
        parse_network(network_cfg(server_url=url))


def test_an_ssid_is_at_most_32_bytes():
    assert parse_network(network_cfg(wifi={"ssid": "x" * 32})).wifi_ssid == "x" * 32
    with pytest.raises(ConfigError, match=r"client.wifi.ssid must be 32 bytes or fewer \(got 34\)"):
        parse_network(network_cfg(wifi={"ssid": "é" * 17}))


@pytest.mark.parametrize("length", [7, 64])
def test_a_password_is_8_to_63_characters(length):
    with pytest.raises(ConfigError, match=f"client.wifi.password must be 8 to 63 characters \\(got {length}\\)"):
        parse_network(network_cfg(wifi={"password": "x" * length}))
    for good in (8, 63):
        assert parse_network(network_cfg(wifi={"password": "x" * good})).wifi_password == "x" * good


@pytest.mark.parametrize("key, value", [
    ("password", 12345678),         # YAML reads unquoted digits as a number
    ("password", True),             # and yes as true
    ("ssid", 2024),
])
def test_a_wifi_value_that_yaml_did_not_read_as_text_is_refused(key, value):
    with pytest.raises(ConfigError, match=f"client.wifi.{key} must be text: put it in quotes"):
        parse_network(network_cfg(wifi={key: value}))


@pytest.mark.parametrize("host", ["epd.local:1883", "mqtt://epd.local", "epd local"])
def test_an_mqtt_host_is_a_host_alone(host):
    with pytest.raises(ConfigError, match="client.mqtt_host must be a host name or address alone"):
        parse_network(network_cfg(mqtt_host=host))
