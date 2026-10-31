"""The settings page, on Flask's test client, with no project's fields."""
import pytest
from bs4 import BeautifulSoup
from flask import Flask

from epd_server.login import Login, SignInSite, guard
from epd_server.settings_form import Field, Form, Group, Tab
from epd_server.settings_page import READ_ONLY, save, save_flow, settings_blueprint

TEXT = """\
---
# Mine.
server:
  port: 8080  # the panel
weather:
  apikey: SECRET-KEY
"""

FORM = Form((
    Tab("server", "Server", (Group("Network", (
        Field("server.port", "Port", "", "int", 8080, minimum=1, maximum=65535, refused="Choose another port."),
        Field("server.note", "Note", "", when="server.port=1|2"),
    )),)),
    Tab("weather", "Weather", (Group("Provider", (
        Field("weather.apikey", "API key", "", "secret"),
        Field("weather.token", "Token", "", "secret", hint="Paste it here"),
        Field("display.schedule", "Wake times", "", "times", {"type": "times", "09:00:00": "today"}, env=False),
    )),)),
))


class Site:
    def __init__(self, path, *, login=None, refuse=None, live=()):
        self.restarts = 0
        self.taken = []
        self.path = path
        app = Flask(__name__)

        def check(text):
            if refuse:
                raise ValueError(refuse)

        def restart():
            self.restarts += 1

        app.register_blueprint(settings_blueprint(FORM, str(path), check, restart=restart, login=login,
                                                  live_keys=live, take_live=self.taken.append))
        if login is not None:
            guard(app, login, SignInSite("t", home="/settings"))
        self.app = app
        self.client = app.test_client()


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(TEXT)
    return p


@pytest.fixture
def site(path):
    return Site(path)


def soup(rsp):
    return BeautifulSoup(rsp.data, "html.parser")


def post(site, action="save", **fields):
    data = {k.replace("__", "."): v for k, v in fields.items()}
    return site.client.post("/settings", data={"mode": "form", "action": action, **data})


# ── What the page shows ──────────────────────────────────────────────

def test_the_page_has_a_tab_for_each_and_the_values(site):
    page = soup(site.client.get("/settings"))
    assert [a["data-tab"] for a in page.select("nav.tabs a")] == ["server", "weather"]
    assert page.find(id="f-server-port")["value"] == "8080"
    assert page.find(attrs={"data-field": "server.note"})["data-when"] == "server.port=1|2"


def test_a_secret_never_reaches_the_page(site):
    rsp = site.client.get("/settings")
    assert b"SECRET-KEY" not in rsp.data
    assert soup(rsp).find(id="f-weather-apikey")["placeholder"] == "Leave blank to keep it"
    assert soup(rsp).find(id="f-weather-token")["placeholder"] == "Paste it here"
    assert rsp.headers["Cache-Control"] == "no-store"


def test_a_field_an_environment_variable_sets_is_locked_and_says_so(path, monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "1234")
    page = soup(Site(path).client.get("/settings"))
    assert page.find(id="f-server-port")["value"] == "1234"
    assert page.find(id="f-server-port").has_attr("disabled")
    assert "Set by SERVER_PORT on the server." in page.text


def test_a_secret_an_environment_variable_sets_does_not_show(path, monkeypatch):
    monkeypatch.setenv("WEATHER_APIKEY", "FROM-ENV")
    rsp = Site(path).client.get("/settings")
    assert b"FROM-ENV" not in rsp.data and b"SECRET-KEY" not in rsp.data


def test_a_read_only_file_is_named_and_save_is_off(path, site):
    path.chmod(0o444)
    try:
        import os
        if os.access(path, os.W_OK):
            pytest.skip("running as root")
        page = soup(site.client.get("/settings"))
        assert READ_ONLY in page.text and page.find(id="save").has_attr("disabled")
        assert post(site, server__port="9090").status_code == 403
    finally:
        path.chmod(0o644)


def test_the_page_loads_a_projects_stylesheet_after_its_own(path):
    app = Flask(__name__)
    app.register_blueprint(settings_blueprint(FORM, str(path), lambda t: None, restart=lambda: None,
                                              styles=("mine.css",), title="Mine"))
    page = soup(app.test_client().get("/settings"))
    assert [link["href"] for link in page.select("link[rel=stylesheet]")] == ["settings/assets/settings.css", "mine.css"]
    assert page.h1.text == "Mine"


def test_the_page_links_to_other_pages_and_names_the_password_variable(path, tmp_path):
    app = Flask(__name__)
    app.register_blueprint(settings_blueprint(FORM, str(path), lambda t: None, restart=lambda: None,
                                              links=(("install", "Install firmware"),), password_env="MY_PASSWORD",
                                              login=Login("", str(tmp_path / "login.json"))))
    page = soup(app.test_client().get("/settings"))
    assert page.select_one(".links a")["href"] == "install"
    assert "Set MY_PASSWORD to turn on sign-in." in page.text


def test_the_assets_serve_and_nothing_else_does(site):
    assert site.client.get("/settings/assets/settings.js").status_code == 200
    assert site.client.get("/settings/assets/settings.css").status_code == 200
    assert site.client.get("/settings/assets/config.yaml").status_code == 404


# ── A review, a check ────────────────────────────────────────────────

def test_a_review_lists_the_changes_and_writes_nothing(path, site):
    rsp = post(site, "review", server__port="9090")
    assert rsp.json == {"changes": [{"name": "Server · Port", "old": "8080", "new": "9090"}], "same": False}
    assert path.read_text() == TEXT and site.restarts == 0


def test_a_review_says_a_secret_changed_and_not_what_to(site):
    rsp = post(site, "review", weather__apikey="NEW-KEY")
    assert rsp.json["changes"] == [{"name": "Weather · API key", "old": "set", "new": "changed"}]
    assert b"SECRET-KEY" not in rsp.data and b"NEW-KEY" not in rsp.data


def test_a_check_says_there_are_no_problems_and_lists_the_changes(path, site):
    page = soup(post(site, "check", server__port="9090"))
    assert "No problems found" in page.text
    assert page.find(id="changes") is not None and path.read_text() == TEXT


def test_a_check_with_nothing_changed_says_so(site):
    assert "Nothing to save." in soup(post(site, "check", server__port="8080")).text


# ── A save ───────────────────────────────────────────────────────────

def test_a_save_keeps_comments_makes_a_backup_and_restarts(path, site):
    rsp = post(site, server__port="9090")
    assert path.read_text() == TEXT.replace("port: 8080", "port: 9090")
    assert (path.parent / "config.yaml.bak").read_text() == TEXT
    assert site.restarts == 1 and b"restarting" in rsp.data


def test_a_blank_secret_keeps_the_value(path, site):
    post(site, weather__apikey="", server__port="9090")
    assert "apikey: SECRET-KEY" in path.read_text()


def test_a_new_secret_is_saved(path, site):
    post(site, weather__apikey="NEW-KEY")
    assert "apikey: NEW-KEY" in path.read_text()


def test_a_save_of_only_live_keys_does_not_restart(path):
    site = Site(path, live=("weather.apikey",))
    rsp = post(site, weather__apikey="NEW-KEY")
    assert site.restarts == 0 and rsp.status_code == 303
    assert "NEW-KEY" in site.taken[0]


def test_a_save_of_a_live_key_and_another_restarts(path):
    site = Site(path, live=("weather.apikey",))
    post(site, weather__apikey="NEW-KEY", server__port="9090")
    assert site.restarts == 1 and not site.taken


def test_wake_times_save_as_a_schedule_in_order(path, site):
    data = {"mode": "form", "action": "save", "display.schedule": "1",
            "display.schedule.at": ["10:00", "08:30:15"], "display.schedule.pool": ["b", "a"]}
    site.client.post("/settings", data=data)
    assert 'display:\n  schedule:\n    type: times\n    "08:30:15": a\n    "10:00:00": b\n' in path.read_text()


def test_restore_puts_the_backup_back_and_restarts(path, site):
    post(site, server__port="9090")
    site.client.post("/settings", data={"mode": "restore", "action": "save"})
    assert path.read_text() == TEXT and site.restarts == 2


def test_restore_with_no_backup_says_so(site):
    rsp = site.client.post("/settings", data={"mode": "restore", "action": "save"})
    assert rsp.status_code == 404 and "No earlier version" in soup(rsp).text


# ── A refusal ────────────────────────────────────────────────────────

def test_a_bad_value_names_the_field_and_the_file_stays(path, site):
    rsp = post(site, server__port="x")
    assert rsp.status_code == 400
    assert soup(rsp).find(id="f-server-port-problem").text == "Enter a whole number."
    assert path.read_text() == TEXT and site.restarts == 0


def test_a_refused_page_keeps_what_was_typed_but_no_secret(site):
    page = soup(post(site, server__port="x", weather__token="TYPED-SECRET"))
    assert page.find(id="f-server-port")["value"] == "x"
    assert "TYPED-SECRET" not in str(page)


def test_the_servers_check_refuses_with_its_words_or_the_fields(path):
    site = Site(path, refuse="server.port must differ")
    rsp = post(site, server__port="9090")
    assert rsp.status_code == 400 and path.read_text() == TEXT
    assert soup(rsp).find(id="f-server-port-problem").text == "Choose another port."


def test_a_review_refusal_is_json(site):
    rsp = post(site, "review", server__port="x")
    assert rsp.status_code == 400
    assert rsp.json == {"problem": "Server · Port: Enter a whole number.", "field": "server.port",
                        "error": "Enter a whole number."}


@pytest.mark.parametrize("broken", ["server: [\n", "- a\n- b\n"])
def test_a_broken_file_says_so_and_can_be_restored(path, site, broken):
    (path.parent / "config.yaml.bak").write_text(TEXT)
    path.write_text(broken)
    page = soup(site.client.get("/settings"))
    assert "Fix it on the server" in page.find(id="problem").text
    assert page.find("button", string="Restore the previous version") is not None
    assert post(site, server__port="9090").status_code == 400
    site.client.post("/settings", data={"mode": "restore", "action": "save"})
    assert path.read_text() == TEXT


def test_a_key_written_twice_names_both_lines(path, site):
    path.write_text("a: 1\na: 2\n")
    assert "on lines 1 and 2" in soup(site.client.get("/settings")).find(id="problem").text


# ── The sign-in ──────────────────────────────────────────────────────

@pytest.fixture
def login(tmp_path):
    return Login("pw", str(tmp_path / "login.json"))


def test_a_save_needs_the_sign_in(path, login):
    site = Site(path, login=login)
    assert site.client.get("/settings").status_code == 401
    assert post(site, server__port="9090").status_code == 401
    assert path.read_text() == TEXT


def test_the_page_shows_the_token_and_replaces_it(path, login):
    site = Site(path, login=login)
    site.client.post("/login", data={"password": "pw"})
    old = login.token
    assert soup(site.client.get("/settings")).find(id="access-token")["value"] == old
    assert site.client.post("/settings/token").headers["Location"] == "../settings"
    assert login.token != old


def test_with_no_password_the_page_says_anyone_can_change_it(path, tmp_path):
    site = Site(path, login=Login("", str(tmp_path / "login.json")))
    page = soup(site.client.get("/settings"))
    assert "anyone on the network" in page.text and page.find(id="access-token") is None


# ── The save flow, as another page uses it ───────────────────────────

def flow(path, **fields):
    from werkzeug.datastructures import MultiDict
    return save_flow(FORM, str(path), MultiDict(fields), lambda t: None, restart=lambda: None)


def test_the_flow_says_what_it_did(path):
    assert flow(path, action="review", **{"server.port": "9090"}).state == "review"
    assert flow(path, action="check", **{"server.port": "8080"}).same
    assert flow(path, action="save", **{"server.port": "8080"}).state == "same"
    out = flow(path, action="save", **{"server.port": "9090"})
    assert out.state == "restarted" and "9090" in out.written


def test_the_flow_refuses_a_mode_it_does_not_know(path, site):
    with pytest.raises(ValueError):
        flow(path, mode="other")
    assert site.client.post("/settings", data={"mode": "other"}).status_code == 400


def test_the_flow_says_why_a_write_failed(path, monkeypatch):
    def refused(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr("epd_server.settings_page.shutil.copy", refused)
    out = flow(path, action="save", **{"server.port": "9090"})
    assert (out.state, out.status, out.problem) == ("refused", 500, "Save failed: Permission denied.")


def test_a_saved_file_ends_in_a_newline(path):
    assert save(str(path), "a: 1") == "a: 1\n" and path.read_text() == "a: 1\n"


def test_the_backup_keeps_the_files_permissions(path):
    path.chmod(0o600)
    save(str(path), "a: 1\n")
    assert (path.parent / "config.yaml.bak").stat().st_mode & 0o777 == 0o600
