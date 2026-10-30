"""A settings form over config.yaml, with no project's own fields."""
import pytest
from werkzeug.datastructures import MultiDict

from epd_server.config_file import MISSING, read
from epd_server.settings_form import (Field, FieldError, Form, Group, Kind, Tab, default_of, host_zone,
                                      initial, input_text, scaled, words_of)

TEXT = """\
# The server's own settings.
server:
  port: 8080  # the panel fetches from here
weather:
  metric: true
display:
  pools:
    today: [today.png]  # the morning
"""

PORT = Field("server.port", "Port", "", "int", 8080, minimum=1, maximum=65535)
ZONE = Field("server.timezone", "Time zone", "", "zone", lambda cfg: host_zone())
METRIC = Field("weather.metric", "Metric", "", "bool", True)
KEY = Field("weather.apikey", "API key", "", "password")
SERVICE = Field("weather.service", "Provider", "", "choice", "mock",
                choices=(("mock", "Made up"), ("meteireann", "Met Éireann")))
WAIT = Field("server.wait_s", "Wait", "", "int", 300, unit="minutes", scale=60)
RATIO = Field("image.ratio", "Ratio", "", "number", 1)
AT = Field("server.at", "At", "", "time")
ORDER = Field("server.order", "Order", "", "order")
POOLS = Field("display.pools", "Sets", "", "pools", env=False)
TAKE_OFF = Field("server.note", "Note", "")
WIFI = Field("client.wifi.ssid", "Wi-Fi name")

FORM = Form(
    (Tab("server", "Server", (Group("Network", (PORT, ZONE, WAIT, AT, ORDER, TAKE_OFF)),)),
     Tab("weather", "Weather", (Group("Provider", (SERVICE, KEY, METRIC, RATIO)),
                                Group("Sets", (POOLS,)))),),
    extra=(WIFI,), extra_title="Install",
)


def posted(**values):
    """A form with ``values``, whose keys write dots as double underscores."""
    return MultiDict({k.replace("__", "."): v for k, v in values.items()})


# ── What the inputs show ─────────────────────────────────────────────

def test_a_field_shows_the_files_value_or_its_default():
    shown = FORM.shown(read(TEXT))
    assert shown["server.port"] == "8080"
    assert shown["weather.service"] == "mock"
    assert shown["weather.metric"] == "true"
    assert shown["weather.apikey"] == ""


def test_a_callable_default_gets_the_file():
    assert default_of(Field("a", "A", default=lambda cfg: cfg["x"]), {"x": 3}) == 3


def test_a_scaled_field_shows_the_inputs_units():
    assert FORM.shown(read("server:\n  wait_s: 600\n"))["server.wait_s"] == "10"
    assert scaled(WAIT, 90) == 1.5
    assert input_text(WAIT, 120) == "2"


def test_rows_show_as_rows_and_have_no_default():
    assert FORM.shown(read(TEXT))["display.pools"] == [("today", "today.png")]
    assert "display.pools" not in FORM.defaults(read(TEXT))


def test_defaults_leave_out_a_field_with_none():
    defaults = FORM.defaults({})
    assert defaults["server.port"] == "8080" and "weather.apikey" not in defaults


def test_initial_gives_rows_as_text_to_compare():
    assert initial([("a", "b")]) == '[["a","b"]]' and initial("x") == "x"


# ── Parsing ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("f, raw, value", [
    (PORT, " 80 ", 80), (WAIT, "2", 120), (RATIO, "1.5", 1.5), (RATIO, "2", 2), (METRIC, "true", True),
    (METRIC, "false", False), (SERVICE, "meteireann", "meteireann"), (AT, "7:05", "07:05"),
    (ORDER, "a.png, b.png,", ["a.png", "b.png"]), (KEY, " kept spaces ", " kept spaces "),
    (ZONE, " Europe/Dublin ", "Europe/Dublin"), (PORT, "", None),
])
def test_a_good_value(f, raw, value):
    assert FORM.parse(f, raw) == value


@pytest.mark.parametrize("f, raw, words", [
    (PORT, "x", "Enter a whole number."), (PORT, "0", "Enter 1 or more."), (PORT, "70000", "Enter 65535 or less."),
    (RATIO, "x", "Enter a number."), (RATIO, "inf", "Enter a number."),
    (SERVICE, "x", "Choose Made up or Met Éireann."), (AT, "25:00", "Enter a time as HH:MM."),
])
def test_a_bad_value_says_what_to_enter(f, raw, words):
    with pytest.raises(FieldError) as caught:
        FORM.parse(f, raw)
    assert str(caught.value) == words


# ── Applying a form ──────────────────────────────────────────────────

def test_a_new_value_keeps_the_comments():
    edit = FORM.apply(TEXT, posted(server__port="9090"))
    assert edit.text == TEXT.replace("port: 8080", "port: 9090")
    assert edit.changed == ["server.port"] and not edit.errors


def test_a_field_the_form_leaves_out_stays():
    assert FORM.apply(TEXT, posted()).text == TEXT


def test_the_default_is_not_written():
    edit = FORM.apply(TEXT, posted(weather__service="mock"))
    assert edit.text == TEXT and edit.changed == []


def test_an_empty_field_takes_the_key_out():
    text = "server:\n  note: hello\n  port: 1\n"
    edit = FORM.apply(text, posted(server__note=""))
    assert read(edit.text) == {"server": {"port": 1}} and edit.changed == ["server.note"]


def test_a_bad_value_changes_nothing_and_names_the_field():
    edit = FORM.apply(TEXT, posted(server__port="x", weather__metric="false"))
    assert edit.text == TEXT and edit.errors == {"server.port": "Enter a whole number."}


def test_a_field_an_environment_variable_sets_is_left_alone(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "1234")
    edit = FORM.apply(TEXT, posted(server__port="9090"))
    assert edit.text == TEXT


def test_a_field_can_refuse_the_environment():
    assert POOLS.env_value() is None and POOLS.env_name == "DISPLAY_POOLS"


def test_pools_keep_their_comments_and_refuse_a_duplicate():
    form = posted(display__pools="1")
    form.setlist("display.pools.name", ["today", "new"])
    form.setlist("display.pools.pages", ["today.png", "a.png, b.png"])
    edit = FORM.apply(TEXT, form)
    assert read(edit.text)["display"]["pools"] == {"today": ["today.png"], "new": ["a.png", "b.png"]}
    assert "# the morning" in edit.text

    form.setlist("display.pools.name", ["same", "same"])
    assert FORM.apply(TEXT, form).errors == {"display.pools": "Two sets are named same. Rename one."}


def test_removing_every_pool_is_refused():
    form = posted(display__pools="1")
    assert FORM.apply(TEXT, form).errors == {"display.pools": "Add at least one pool."}


def test_a_projects_own_kind_shows_parses_and_writes():
    class Upper(Kind):
        def show(self, f, value, cfg):
            return "" if value is MISSING else value.lower()

        def parse(self, f, raw):
            if not raw:
                raise FieldError("Enter a word.")
            return raw.upper()

    form = Form((Tab("t", "T", (Group("G", (Field("a.b", "B", kind="upper"),)),)),), kinds={"upper": Upper()})
    edit = form.apply("a:\n  b: X\n", posted(a__b="word"))
    assert read(edit.text) == {"a": {"b": "WORD"}}
    assert form.shown(read(edit.text))["a.b"] == "word"
    assert form.apply("a: 1\n", posted(a__b="")).errors == {"a.b": "Enter a word."}


def test_fields_written_together_go_through_their_function():
    def together(cfg, values, put):
        put(("w",), {"from": values["w.from"]} if values["w"] else {})
        return ["w"]

    fields = (Field("w", "On", kind="bool"), Field("w.from", "From", kind="time"))
    form = Form((Tab("t", "T", (Group("G", fields),)),), joint={"w": together})
    assert read(form.apply("a: 1\n", posted(w="true", w__from="07:00")).text)["w"] == {"from": "07:00"}


# ── Words ────────────────────────────────────────────────────────────

def test_changes_are_listed_in_the_forms_order_in_words():
    old, new = read(TEXT), read(TEXT.replace("metric: true", "metric: false").replace("8080", "9090"))
    assert FORM.changes(old, new) == [
        {"name": "Server · Port", "old": "8080", "new": "9090"},
        {"name": "Weather · Metric", "old": "on", "new": "off"},
    ]


def test_a_scaled_change_has_its_unit():
    changes = FORM.changes({"server": {"wait_s": 60}}, {"server": {"wait_s": 120}})
    assert changes == [{"name": "Server · Wait", "old": "1 minutes", "new": "2 minutes"}]


def test_a_setting_with_no_field_is_named_by_its_key():
    assert FORM.changes({"x": {"y": 1}}, {"x": {"y": 2}})[0]["name"] == "x.y"


def test_an_extra_field_is_named_by_its_page():
    assert FORM.name_of(("client", "wifi", "ssid")) == "Install · Wi-Fi name"


def test_a_shared_label_names_its_group():
    a, b = Field("a.x", "Same"), Field("b.x", "Same")
    form = Form((Tab("t", "T", (Group("One", (a,)), Group("Two", (b,)))),))
    assert form.name_of(("b", "x")) == "T · Two · Same"


def test_a_problem_from_the_servers_check_finds_its_field_and_tab():
    assert FORM.locate("server.port must be a port") == ("server.port", "server")
    assert FORM.locate("weather.other is wrong") == (None, "weather")
    assert FORM.locate("nothing here") == (None, None)


def test_a_running_value_that_differs_is_in_words_with_its_unit():
    f = Field("a.t", "T", kind="number", unit="°C")
    form = Form((Tab("t", "T", (Group("G", (f,)),)),))
    assert form.in_use({"a": {"t": 4}}, {"a": {"t": 5}}) == {"a.t": "4 °C"}


def test_words_of_a_value():
    assert [words_of(v) for v in (MISSING, True, False, ["a", "b"], {}, 3)] == \
        ["not set", "on", "off", "a, b", "off", "3"]
