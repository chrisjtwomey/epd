"""The sign-in: which routes it guards, its cookie, wrong tries, the access
token, the Origin check, and a reverse proxy."""
import json

import pytest
from flask import Flask
from freezegun import freeze_time

import epd_server.login as lg
from epd_server.login import Login, SignInSite, board_route, guard, sign_in_html

PASSWORD = "correct horse"
HTML = {"Accept": "text/html,application/xhtml+xml"}
JSON = {"Accept": "application/json"}
SITE = SignInSite("test", data=frozenset({"/network.bin", "/status"}), home="/web/", prefix="/web")
COOKIE = SITE.cookie
SECURE_COOKIE = SITE.secure_cookie


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


def site(login: Login, reverse_proxy: bool = False) -> Flask:
    """Every route answers "ok", behind ``login``."""
    app = Flask(__name__)

    @app.route("/", methods=["GET", "POST"])
    @app.route("/<path:name>", methods=["GET", "POST"])
    def anything(name=""):
        return "ok"

    guard(app, login, SITE, reverse_proxy)
    return app


@pytest.fixture
def login(tmp_path, clock):
    return Login(PASSWORD, str(tmp_path / "login.json"), now=clock)


@pytest.fixture
def client(login):
    return site(login).test_client()


def sign_in(client, password=PASSWORD, address="10.0.0.2", **kw):
    return client.post("/web/login", data={"password": password, "next": "/web/"},
                       environ_base={"REMOTE_ADDR": address}, **kw)


# ── Which routes need a sign-in ──────────────────────────────────────

BOARD_ROUTES = [("GET", "/"), ("GET", "/today.png"), ("HEAD", "/today.png"), ("GET", "/firmware.bin"),
                ("GET", "/firmware.merged.bin"), ("GET", "/install-firmware.sh"), ("POST", "/pair")]
PAGE_FILES = [("GET", "/static/install/install.js"), ("GET", "/install/install.js")]
PEOPLE_ROUTES = [("GET", "/web/"), ("GET", "/web/config"), ("POST", "/web/config"),
                 ("GET", "/network.bin"), ("GET", "/install"), ("GET", "/status"),
                 ("GET", "/web/sub/page.png"), ("POST", "/today.png"),
                 ("GET", "/anything-new"), ("POST", "/anything-new")]


@pytest.mark.parametrize("method, path", BOARD_ROUTES + PAGE_FILES)
def test_the_boards_routes_and_a_pages_files_need_no_sign_in(method, path):
    assert board_route(method, path)


@pytest.mark.parametrize("method, path", PEOPLE_ROUTES)
def test_every_other_route_needs_a_sign_in(method, path):
    assert not board_route(method, path)


@pytest.mark.parametrize("method, path", BOARD_ROUTES)
def test_a_board_reaches_its_routes_with_a_password_set(client, method, path):
    assert client.open(path, method=method).status_code == 200


def test_a_page_asks_a_browser_to_sign_in_and_comes_back_after(client):
    rsp = client.get("/web/config?tab=dock", headers=HTML)
    assert rsp.status_code == 303
    assert rsp.headers["Location"] == "/web/login?next=/web/config%3Ftab%3Ddock"
    assert b'name="next" value="/web/config?tab=dock"' in client.get(rsp.headers["Location"]).data
    rsp = client.post("/web/login", data={"password": PASSWORD, "next": "/web/config?tab=dock"})
    assert (rsp.status_code, rsp.headers["Location"]) == (303, "/web/config?tab=dock")
    assert client.get("/web/config", headers=HTML).data == b"ok"


def test_a_script_on_a_page_that_has_signed_out_is_told_to_reload(client):
    rsp = client.post("/web/config", headers=JSON)
    assert rsp.status_code == 401
    assert rsp.json == {"problem": lg.SIGNED_OUT}


def test_network_bin_needs_a_sign_in(client):
    assert client.get("/network.bin?product=my-display").status_code == 401
    sign_in(client)
    assert client.get("/network.bin?product=my-display").data == b"ok"


def test_the_terminal_install_signs_in_with_the_password_alone(client):
    rsp = client.post("/web/login", data={"password": PASSWORD})
    assert rsp.status_code == 303
    assert client.get("/network.bin?product=my-display").data == b"ok"


def test_with_no_password_every_route_is_open(tmp_path):
    login = Login("", str(tmp_path / "login.json"))
    client = site(login).test_client()
    for method, path in PEOPLE_ROUTES:
        assert client.open(path, method=method, headers=HTML).status_code == 200, path
    assert client.get("/web/login?next=/web/logs").headers["Location"] == "/web/logs"
    assert not (tmp_path / "login.json").exists()
    assert login.token == "" and not login.token_ok("")


# ── The sign-in ──────────────────────────────────────────────────────

def test_a_sign_in_over_http_sets_a_cookie_for_30_days_that_scripts_cannot_read(client):
    cookie = sign_in(client).headers["Set-Cookie"]
    assert cookie.startswith(COOKIE + "=")
    assert "Max-Age=2592000" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "Secure" not in cookie


def test_a_sign_in_over_https_sets_a_secure_cookie_of_its_own(login):
    client = site(login).test_client()
    cookie = client.post("/web/login", data={"password": PASSWORD},
                         base_url="https://epd.local").headers["Set-Cookie"]
    assert cookie.startswith(SECURE_COOKIE + "=") and "Secure" in cookie
    assert client.get("/web/", base_url="https://epd.local").data == b"ok"


def test_a_wrong_password_says_so_and_sets_no_cookie(client):
    rsp = sign_in(client, "wrong")
    assert rsp.status_code == 401 and "Set-Cookie" not in rsp.headers
    assert f'id="problem" role="alert">{lg.WRONG}<'.encode() in rsp.data
    assert client.get("/web/", headers=HTML).status_code == 303


def test_a_sign_in_lasts_30_days(client):
    with freeze_time("2026-10-15 12:00:00") as frozen:
        sign_in(client)
        frozen.tick(30 * 86400 - 60)
        assert client.get("/web/").data == b"ok"
        frozen.tick(120)
        assert client.get("/web/").status_code == 401


def test_sign_out_ends_the_sign_in(client):
    sign_in(client)
    rsp = client.post("/web/logout")
    assert (rsp.status_code, rsp.headers["Location"]) == (303, "/web/login")
    assert client.get("/web/").status_code == 401


def restarted(client, password: str, path: str):
    """A client of a new server on ``path`` with ``password``, holding the cookie ``client`` holds."""
    again = site(Login(password, path)).test_client()
    again.set_cookie(COOKIE, client.get_cookie(COOKIE).value)
    return again


def test_a_new_password_ends_every_sign_in(client, login):
    sign_in(client)
    assert restarted(client, "another one", login.path).get("/web/").status_code == 401


def test_a_sign_in_survives_a_restart(client, login):
    sign_in(client)
    assert restarted(client, PASSWORD, login.path).get("/web/").data == b"ok"


def test_a_cookie_another_server_signed_is_refused(tmp_path, client):
    other = Login(PASSWORD, str(tmp_path / "other.json"))
    client.set_cookie(COOKIE, other.cookie())
    assert client.get("/web/").status_code == 401


@pytest.mark.parametrize("asked", ["//evil.example/", "https://evil.example/", "/\\evil",
                                   "/\t/evil.example/", "/\n/evil.example/", "web/", "/web/login"])
def test_a_sign_in_goes_only_to_a_page_of_this_site(client, asked):
    rsp = client.post("/web/login", data={"password": PASSWORD, "next": asked})
    assert rsp.headers["Location"] == "/web/"


def test_the_keep_file_holds_no_password(login):
    kept = open(login.path).read()
    assert PASSWORD not in kept and set(json.loads(kept)) == {"secret", "token"}


# ── Wrong tries ──────────────────────────────────────────────────────

def test_five_wrong_tries_make_that_address_wait_15_minutes(client, clock):
    for _ in range(lg.TRIES - 1):
        assert sign_in(client, "wrong").status_code == 401
    rsp = sign_in(client, "wrong")
    assert rsp.status_code == 429 and rsp.headers["Retry-After"] == "900"
    assert lg.TOO_MANY.encode() in rsp.data
    assert sign_in(client).status_code == 429
    assert sign_in(client, address="10.0.0.3").status_code == 303
    clock.t += lg.WAIT_S
    assert sign_in(client).status_code == 303


def test_tries_while_waiting_do_not_make_the_wait_longer(client, clock):
    for _ in range(lg.TRIES):
        sign_in(client, "wrong")
    clock.t += lg.WAIT_S - 1
    assert sign_in(client, "wrong").status_code == 429
    clock.t += 1
    assert sign_in(client).status_code == 303


def test_a_right_password_forgets_the_wrong_ones(client):
    for _ in range(lg.TRIES - 1):
        sign_in(client, "wrong")
    sign_in(client)
    client.post("/web/logout")
    assert sign_in(client, "wrong").status_code == 401


def test_wrong_tries_far_apart_do_not_add_up(client, clock):
    for _ in range(lg.TRIES * 2):
        assert sign_in(client, "wrong").status_code == 401
        clock.t += lg.WAIT_S


# ── The token ────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", sorted(SITE.data))
def test_the_access_token_reads_the_data(client, login, path):
    rsp = client.get(path, headers={"Authorization": f"Bearer {login.token}"})
    assert rsp.data == b"ok"


@pytest.mark.parametrize("method, path", [("GET", "/web/config"), ("POST", "/web/config"),
                                          ("GET", "/web/")])
def test_the_access_token_opens_nothing_else(client, login, method, path):
    rsp = client.open(path, method=method, headers={"Authorization": f"Bearer {login.token}"})
    assert rsp.status_code == 401


def test_an_app_without_the_token_is_told_how_to_send_it(client):
    rsp = client.get("/status", headers={"Authorization": "Bearer wrong"})
    assert rsp.status_code == 401 and rsp.json == {"problem": lg.NEEDS_TOKEN}
    assert rsp.headers["WWW-Authenticate"] == 'Bearer realm="test"'


def test_a_replaced_token_reads_nothing(client, login):
    old = login.token
    new = login.replace_token()
    assert new != old and login.token == new
    assert client.get("/status", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.get("/status", headers={"Authorization": f"Bearer {new}"}).data == b"ok"


def test_the_access_token_is_made_once_and_kept_across_a_restart(login):
    assert len(login.token) >= 43
    again = Login(PASSWORD, login.path)
    assert again.token == login.token
    assert again.token_ok(login.token) and not again.token_ok(login.token + "x")


# ── Changes from another site ────────────────────────────────────────

@pytest.mark.parametrize("password", ["", PASSWORD])
def test_a_change_from_another_site_is_refused(tmp_path, password):
    client = site(Login(password, str(tmp_path / "login.json"))).test_client()
    if password:
        sign_in(client)
    for origin in ("http://evil.example", "null", "http://localhost:8443"):
        rsp = client.post("/web/config", headers={"Origin": origin})
        assert rsp.status_code == 403 and rsp.json == {"problem": lg.OTHER_SITE}, origin
    assert client.post("/web/config", headers={"Origin": "http://localhost"}).data == b"ok"
    assert client.post("/web/config").data == b"ok"


def test_a_board_post_from_another_site_is_refused(client):
    rsp = client.post("/sensor-readings", headers={"Origin": "http://evil.example"})
    assert rsp.status_code == 403


def test_a_page_from_another_site_can_still_be_read(client):
    sign_in(client)
    assert client.get("/web/", headers={"Origin": "http://evil.example"}).data == b"ok"


# ── Behind a reverse proxy ───────────────────────────────────────────

PROXIED = {"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Host": "epd.example.com",
           "X-Forwarded-Proto": "https"}


def test_a_trusted_proxy_gives_the_visitors_address_host_and_scheme(login):
    client = site(login, reverse_proxy=True).test_client()
    for _ in range(lg.TRIES):
        sign_in(client, "wrong", headers=PROXIED)
    assert sign_in(client, headers=PROXIED).status_code == 429
    other = {**PROXIED, "X-Forwarded-For": "203.0.113.10"}
    rsp = sign_in(client, headers=other)
    assert rsp.status_code == 303 and "Secure" in rsp.headers["Set-Cookie"]
    rsp = client.post("/web/config", headers={**other, "Origin": "https://epd.example.com"})
    assert rsp.data == b"ok"


def test_without_the_setting_the_proxys_headers_change_nothing(client):
    for i in range(lg.TRIES):
        sign_in(client, "wrong", headers={"X-Forwarded-For": f"203.0.113.{i}"})
    assert sign_in(client).status_code == 429


def test_a_change_through_an_untrusted_proxy_says_how_to_trust_it(client):
    rsp = client.post("/web/config", headers={**PROXIED, "Origin": "https://epd.example.com"})
    assert rsp.status_code == 403 and rsp.json == {"problem": lg.UNTRUSTED_PROXY}


# ── A site's own choices ─────────────────────────────────────────────

def test_a_site_with_no_prefix_signs_in_at_the_root(tmp_path):
    app = Flask(__name__)

    @app.route("/settings")
    def settings():
        return "ok"

    site_ = SignInSite("weather")
    guard(app, Login(PASSWORD, str(tmp_path / "login.json")), site_)
    client = app.test_client()
    rsp = client.get("/settings", headers=HTML)
    assert rsp.headers["Location"] == "/login?next=/settings"
    assert client.post("/login", data={"password": PASSWORD, "next": "/settings"}).status_code == 303
    assert client.get("/settings").data == b"ok"
    assert client.post("/logout").headers["Location"] == "/login"


def test_a_site_draws_its_own_page_and_opens_its_own_routes(tmp_path):
    def drawn(next_path, problem):
        return f"mine {next_path} {problem}"

    site_ = SignInSite("mine", is_open=lambda method, path: path == "/open", page=drawn)
    app = Flask(__name__)

    @app.route("/<name>")
    def anything(name):
        return "ok"

    guard(app, Login(PASSWORD, str(tmp_path / "login.json")), site_)
    client = app.test_client()
    assert client.get("/open").data == b"ok"
    assert client.get("/today.png").status_code == 401, "the site's is_open replaces board_route"
    assert client.get("/login?next=/open").data == b"mine /open "


def test_the_plain_page_escapes_what_it_is_given():
    page = sign_in_html('/x"><script>', "<b>")
    assert "<script>" not in page and "<b>" not in page
