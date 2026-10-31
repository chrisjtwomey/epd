"""A site's sign-in: a password the project gives, a cookie that lasts
SIGNED_IN_S, an access token for other apps, and a check that each change
comes from this site.

    GET  <prefix>/login     the sign-in page; ``next`` is where it goes after
    POST <prefix>/login     the password: the cookie, then ``next``
    POST <prefix>/logout    the cookie gone, then the sign-in page

With no password set, every route is open. With one, every route needs the
cookie except the ones ``SignInSite.is_open`` names and the sign-in itself;
the routes in ``SignInSite.data`` also take the access token. After TRIES wrong
passwords in a row, an address waits WAIT_S.

Each POST, PUT, PATCH or DELETE whose Origin is another site gets 403, with a
password or without: a page on another site could otherwise post to this
one from a visitor's browser.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import math
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from flask import Blueprint, Flask, Response, g, jsonify, make_response, redirect, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix

from .install import INSTALLER

log = logging.getLogger("login")

SIGNED_IN_S = 30 * 86400
TRIES = 5
WAIT_S = 15 * 60

# What a board asks for of epd's routes, and the files the install page loads.
_BOARD_GET = frozenset({"/", "/firmware.bin", "/firmware.merged.bin", "/" + INSTALLER})
_BOARD_POST = frozenset({"/pair"})
_FILE_PREFIXES = ("/static/", "/install/")
CHANGES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FORWARDED = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto")

WRONG = "Wrong password. Try again."
TOO_MANY = f"Too many tries. Try again in {WAIT_S // 60} minutes."
SIGNED_OUT = "Signed out. Reload the page to sign in again."
NEEDS_TOKEN = ("Not signed in. Send the access token from Settings, as "
               "Authorization: Bearer <token>.")
OTHER_SITE = "The request came from another site."
UNTRUSTED_PROXY = ("The request came through a reverse proxy. In config.yaml, set "
                   "server.reverse_proxy to true, then restart the server.")


def board_route(method: str, path: str) -> bool:
    """Whether a request is one of epd's that a board makes with no sign-in, or
    a file the install page loads. A page is any ``.png`` at the top level."""
    if method in ("GET", "HEAD"):
        return path in _BOARD_GET or path.startswith(_FILE_PREFIXES) \
            or (path.count("/") == 1 and path.endswith(".png"))
    return method == "POST" and path in _BOARD_POST


def sign_in_html(next_path: str, problem: str = "") -> str:
    """A plain sign-in page, for a project with no layout of its own."""
    alert = f'<p class="banner problem" id="problem" role="alert">{html.escape(problem)}</p>' if problem else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in</title>
<link rel="stylesheet" href="/static/look/look.css">
<style>
body {{ box-sizing: border-box; max-width: 24rem; margin: 0 auto; padding: 72px 24px 0; }}
form {{ display: grid; gap: 8px; margin-top: 16px; }}
button {{ margin-top: 8px; }}
</style>
</head>
<body>
<h1>Sign in</h1>
{alert}
<form method="post" action="login" id="sign-in-form">
<input type="hidden" name="next" value="{html.escape(next_path, quote=True)}">
<label for="password">Password</label>
<input type="password" id="password" name="password" autocomplete="current-password" autofocus required>
<button type="submit" class="primary">Sign in</button>
</form>
</body>
</html>
"""


@dataclass(frozen=True)
class SignInSite:
    """What differs from one project's sign-in to another's.

    Args:
        name: names the cookies and the access token's realm.
        is_open: whether a method and path need no sign-in.
        data: the paths the access token reads, as well as the cookie.
        home: where a sign-in goes when it was not sent from a page.
        prefix: where the sign-in's own routes sit.
        page: draws the sign-in page, from where it goes after and a problem to show.
    """
    name: str
    is_open: Callable[[str, str], bool] = board_route
    data: frozenset[str] = frozenset({"/network.bin"})
    home: str = "/"
    prefix: str = ""
    page: Callable[[str, str], str] = sign_in_html

    @property
    def cookie(self) -> str:
        return f"{self.name}-sign-in"

    @property
    def secure_cookie(self) -> str:
        # A browser lets no HTTP page set a cookie over a Secure one of the
        # same name, so an HTTPS sign-in has a cookie of its own.
        return f"__Secure-{self.name}-sign-in"

    @property
    def login_path(self) -> str:
        return self.prefix + "/login"

    @property
    def logout_path(self) -> str:
        return self.prefix + "/logout"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Tries:
    """Wrong passwords by address. TRIES in a row, each within WAIT_S of the
    one before, make the address wait WAIT_S from the last; a right one
    forgets the address."""

    def __init__(self, now: Callable[[], float] = time.time):
        self.now = now
        self._by: dict[str, tuple[int, float]] = {}   # wrong in a row, and when the last came
        self._lock = threading.Lock()

    def wait(self, address: str) -> float:
        """The seconds ``address`` must still wait to try again; 0 for none."""
        with self._lock:
            count, last = self._by.get(address, (0, 0.0))
            left = last + WAIT_S - self.now()
            return left if count >= TRIES and left > 0 else 0.0

    def wrong(self, address: str) -> None:
        now = self.now()
        with self._lock:
            for old in [a for a, (_, last) in self._by.items() if now - last >= WAIT_S]:
                del self._by[old]
            count, _ = self._by.get(address, (0, 0.0))
            self._by[address] = (count + 1, now)

    def right(self, address: str) -> None:
        with self._lock:
            self._by.pop(address, None)


class Login:
    """Who may use the site: the password, the cookies signed with it, the
    access token and the wrong tries.

    ``path`` keeps the cookies' secret and the access token. It is written
    only once a password is set, so a server without one keeps no file.
    """

    def __init__(self, password: str, path: str, now: Callable[[], float] = time.time):
        self.password = password
        self.path = path
        self.tries = Tries(now)
        self._lock = threading.Lock()
        self._kept: dict[str, str] = self._read() if password else {}
        if password and not {"secret", "token"} <= self._kept.keys():
            self._kept.setdefault("secret", secrets.token_hex(32))
            self._kept.setdefault("token", secrets.token_urlsafe(32))
            self._write()

    @property
    def on(self) -> bool:
        return bool(self.password)

    def _read(self) -> dict[str, str]:
        try:
            with open(self.path) as f:
                kept = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.error("%s is unreadable (%s): every browser signs in again, and the "
                      "access token is new", self.path, exc)
            return {}
        return kept if isinstance(kept, dict) else {}

    def _write(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        part = self.path + ".part"
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self._kept, f)
        os.replace(part, self.path)

    def _signer(self) -> URLSafeTimedSerializer:
        # The password is part of the key, so a new one ends every sign-in.
        key = hmac.new(bytes.fromhex(self._kept["secret"]), self.password.encode(),
                       hashlib.sha256).digest()
        return URLSafeTimedSerializer(key, salt="sign-in")

    def right(self, given: str) -> bool:
        return hmac.compare_digest(_digest(given), _digest(self.password))

    def cookie(self) -> str:
        return self._signer().dumps("in")

    def signed_in(self, *cookies: str | None) -> bool:
        """Whether one of ``cookies`` is a sign-in this server made, not older
        than SIGNED_IN_S."""
        for value in filter(None, cookies):
            try:
                if self._signer().loads(value, max_age=SIGNED_IN_S) == "in":
                    return True
            except BadSignature:
                pass
        return False

    @property
    def token(self) -> str:
        """The access token; empty with no password, when nothing needs one."""
        return self._kept.get("token", "")

    def replace_token(self) -> str:
        with self._lock:
            self._kept["token"] = secrets.token_urlsafe(32)
            self._write()
        return self.token

    def token_ok(self, given: str) -> bool:
        return bool(self.token and given) and hmac.compare_digest(_digest(given),
                                                                  _digest(self.token))


def _bearer() -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _problem(words: str, status: int) -> Response:
    rsp = jsonify(problem=words)
    rsp.status_code = status
    return rsp


def _page(page: str, status: int = 200) -> Response:
    rsp = make_response(page, status)
    rsp.headers["Cache-Control"] = "no-store"
    return rsp


def guard(app: Flask, login: Login, site: SignInSite, reverse_proxy: bool = False) -> None:
    """Put ``login`` in front of every route of ``app``, and the Origin check
    on every change. With ``reverse_proxy`` the visitor's address, scheme
    and host come from the proxy's X-Forwarded-* headers; without it the
    server ignores them, so nobody can fake an address."""
    if reverse_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    def cookies() -> tuple[str | None, str | None]:
        return request.cookies.get(site.secure_cookie), request.cookies.get(site.cookie)

    def local(path: str) -> str:
        """``path`` when it is a page of this site to go to after a sign-in;
        ``site.home`` when it is not."""
        if not path.startswith("/") or path.startswith("//") or "\\" in path \
                or any(c.isspace() or not c.isprintable() for c in path) \
                or path.startswith(site.login_path):
            return site.home
        return path

    def sign_in_first() -> Response:
        wants_page = "text/html" in request.headers.get("Accept", "")
        if request.method == "GET" and wants_page and request.path not in site.data:
            there = request.full_path.rstrip("?")
            return redirect(f"{site.login_path}?next=" + quote(there, safe="/"), 303)
        if request.method in CHANGES and wants_page:
            return redirect(f"{site.login_path}?next=" + quote(request.path, safe="/"), 303)
        if request.path not in site.data:
            return _problem(SIGNED_OUT, 401)
        rsp = _problem(NEEDS_TOKEN, 401)
        rsp.headers["WWW-Authenticate"] = f'Bearer realm="{site.name}"'
        return rsp

    def same_site_only():
        if request.method not in CHANGES:
            return None
        origin = request.headers.get("Origin")
        if origin is None or origin.lower() == request.host_url.rstrip("/").lower():
            return None
        through_proxy = not reverse_proxy and any(h in request.headers for h in FORWARDED)
        return _problem(UNTRUSTED_PROXY if through_proxy else OTHER_SITE, 403)

    def signed_in_only():
        g.signed_in = login.on and login.signed_in(*cookies())
        if not login.on or g.signed_in or site.is_open(request.method, request.path) \
                or request.path in (site.login_path, site.logout_path):
            return None
        if request.method in ("GET", "HEAD") and request.path in site.data \
                and login.token_ok(_bearer()):
            return None
        return sign_in_first()

    bp = Blueprint("login", __name__, url_prefix=site.prefix or None)

    @bp.route("/login", methods=["GET"])
    def show():
        there = local(request.args.get("next", site.home))
        if not login.on or login.signed_in(*cookies()):
            return redirect(there, 303)
        return _page(site.page(there, ""))

    @bp.route("/login", methods=["POST"])
    def sign_in():
        there = local(request.form.get("next", site.home))
        if not login.on:
            return redirect(there, 303)
        address = request.remote_addr or ""
        if not login.tries.wait(address):
            if login.right(request.form.get("password", "")):
                login.tries.right(address)
                rsp = redirect(there, 303)
                secure = request.is_secure
                rsp.set_cookie(site.secure_cookie if secure else site.cookie, login.cookie(),
                               max_age=SIGNED_IN_S, path="/", secure=secure, httponly=True,
                               samesite="Lax")
                return rsp
            login.tries.wrong(address)
        wait = login.tries.wait(address)
        if not wait:
            return _page(site.page(there, WRONG), 401)
        rsp = _page(site.page(there, TOO_MANY), 429)
        rsp.headers["Retry-After"] = str(math.ceil(wait))
        return rsp

    @bp.route("/logout", methods=["POST"])
    def sign_out():
        rsp = redirect(site.login_path, 303)
        rsp.delete_cookie(site.cookie, path="/")
        rsp.delete_cookie(site.secure_cookie, path="/", secure=True)
        return rsp

    app.before_request(same_site_only)
    app.before_request(signed_in_only)
    app.register_blueprint(bp)
