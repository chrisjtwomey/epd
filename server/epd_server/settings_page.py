"""config.yaml in the browser: a :class:`~epd_server.settings_form.Form` in tabs,
a check, a review of the changes, a save and a restart.

    GET  <url>                  the page
    POST <url>                  mode=form: the form's values written into the file
                                mode=restore: config.yaml.bak
                                action=check: whether the server would start on it
                                action=review: the same, and the changes, as JSON
                                action=save: the same check, the old file kept as
                                config.yaml.bak, the new one written, and the
                                server restarted on it
    POST <url>/token            a new access token in place of the old
    GET  <url>/assets/<name>    the page's script and stylesheet

Put a sign-in in front of it: the page changes the server's settings. The page
is plain, and works without its script; pass ``styles`` for a project's own look.
"""
from __future__ import annotations

import html
import json
import logging
import os
import shutil
import sys
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from flask import Blueprint, Response, abort, jsonify, make_response, redirect, request, send_from_directory

from .config_file import FormError, read, twice
from .login import Login
from .settings_form import Field, Form, Group, Tab, initial

__all__ = ["NO_BACKUP", "NOTHING", "READ_ONLY", "Outcome", "restart_soon", "save", "save_flow", "settings_blueprint"]

log = logging.getLogger("settings")

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "static", "settings")
_ASSETS = ("settings.js", "settings.css")
# Served from the DisplayServer's static folder, which needs no sign-in.
LOOK_CSS = "static/look/look.css"

READ_ONLY = "Cannot save: config.yaml is read-only. Mount it writable, then restart the server."
NOTHING = "Nothing to save."
NO_PROBLEMS = "No problems found. Save and restart to apply these changes."
SAVED = "Settings saved."
NO_BACKUP = "No earlier version to restore."
_E = html.escape


def restart_soon(delay_s: float = 1.0) -> None:
    """Start this process again on the config as it now is, once the response
    to the request that asked for it has gone out."""
    def again():
        log.info("restarting on the new config")
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:])
    threading.Timer(delay_s, again).start()


def save(path: str, text: str) -> str:
    """Keep ``path`` as it was beside it, then write ``text`` over it in place:
    a file mounted into a container on its own cannot be replaced by a rename.
    Returns what it wrote: ``text`` ending in a newline."""
    shutil.copy(path, path + ".bak")
    written = text if text.endswith("\n") else text + "\n"
    with open(path, "w") as f:
        f.write(written)
    return written


@dataclass
class Outcome:
    """What a posted form did. A page draws it in its own way.

    ``state`` is one of: ``refused``, with ``problem`` and ``status``, and for a
    field ``key``, ``tab`` and ``errors``; ``review``, with ``changes`` and ``same``;
    ``checked``, with ``changes`` and ``same``; ``same``, a save with nothing to
    write; ``live``, saved and taken without a restart; ``restarted``, saved and
    restarting.
    """
    state: str
    problem: str = ""
    status: int = 200
    key: str | None = None
    tab: str | None = None
    errors: dict[str, str] = field(default_factory=dict)
    changes: list[dict] = field(default_factory=list)
    same: bool = False
    written: str = ""


def save_flow(form: Form, path: str, posted, check: Callable[[str], None], *,
              restart: Callable[[], None], live_keys: Iterable[str] = (),
              take_live: Callable[[str], None] | None = None, read_only: str = READ_ONLY) -> Outcome:
    """One post of a settings form: ``mode`` of ``form`` or ``restore``, and an
    ``action`` of ``check``, ``review`` or ``save``.

    The check runs on every action, and nothing is written unless it passes.

    Raises:
        ValueError: a mode this does not know.
    """
    mode = posted.get("mode", "form")
    action = posted.get("action", "check")
    with open(path) as f:
        current = f.read()

    changed: list[str] = []
    if mode == "restore":
        try:
            with open(path + ".bak") as f:
                text = f.read()
        except OSError:
            return Outcome("refused", NO_BACKUP, 404)
    elif mode == "form":
        try:
            edit = form.apply(current, posted)
        except FormError as exc:
            return Outcome("refused", str(exc), 400)
        if edit.errors:
            key = next(f.key for f in form.fields if f.key in edit.errors)
            return Outcome("refused", f"{form.name_of(form.by_key[key].path)}: {edit.errors[key]}", 400,
                           key, form.tab_of.get(key), edit.errors)
        text, changed = edit.text, edit.changed
    else:
        raise ValueError(f"no mode {mode}")

    try:
        check(text)
    except ValueError as exc:
        problem = str(exc)
        if mode != "form":
            return Outcome("refused", problem, 400)
        key, tab = form.locate(problem)
        errors = {}
        if key:
            f = form.by_key[key]
            if f.refused:
                problem = f"{form.name_of(f.path)}: {f.refused}"
            errors[key] = f.refused or problem
        return Outcome("refused", problem, 400, key, tab, errors)

    if action != "save":
        changes = form.changes(read(current), read(text))
        return Outcome("review" if action == "review" else "checked", changes=changes, same=text == current)
    if text == current:
        return Outcome("same", same=True)
    if not os.access(path, os.W_OK):
        return Outcome("refused", read_only, 403)
    try:
        written = save(path, text)
    except OSError as exc:
        return Outcome("refused", f"Save failed: {exc.strerror}.", 500)
    if take_live is not None and mode == "form" and changed and set(changed) <= frozenset(live_keys):
        take_live(written)
        return Outcome("live", written=written)
    restart()
    return Outcome("restarted", written=written)


def _id(key: str) -> str:
    return "f-" + key.replace(".", "-")


def _input(f: Field, value: str, locked: bool) -> str:
    attrs = f'id="{_id(f.key)}" name="{_E(f.key)}" data-key="{_E(f.key)}"'
    if locked:
        attrs += " disabled"
    if f.hint:
        attrs += f' placeholder="{_E(f.hint)}"'
    if f.kind == "bool":
        checked = " checked" if value == "true" else ""
        hidden = "" if locked else f'<input type="hidden" name="{_E(f.key)}" value="false">'
        return f'{hidden}<input type="checkbox" value="true" {attrs}{checked}>'
    if f.kind in ("choice", "stops"):
        options = "".join(f'<option value="{_E(c, quote=True)}"{" selected" if c == value else ""}>{_E(w)}</option>'
                          for c, w in f.choices)
        return f"<select {attrs}>{options}</select>"
    if f.kind in ("int", "number"):
        step = str(f.step) if f.kind == "int" else "any"
        limits = (f' min="{f.minimum:g}"' if f.minimum is not None else "") + \
                 (f' max="{f.maximum:g}"' if f.maximum is not None else "")
        return f'<input type="number" step="{step}"{limits} {attrs} value="{_E(value, quote=True)}">'
    kind = "password" if f.kind == "password" else "text"
    return (f'<input type="{kind}" spellcheck="false" autocomplete="off" {attrs} '
            f'value="{_E(value, quote=True)}">')


class _Page:
    """One render of the page."""

    def __init__(self, form: Form, text: str, values: dict, errors: dict, locked: bool,
                 login: Login | None, url: str, styles: Iterable[str], title: str,
                 links: Iterable[tuple[str, str]] = ()):
        self.form = form
        self.cfg = read(text) if text is not None else {}
        self.values = {**form.shown(self.cfg), **values}
        self.saved_values = form.shown(self.cfg)
        self.errors = errors
        self.locked = locked
        self.login = login
        self.url = url
        self.styles = tuple(styles)
        self.title = title
        self.links = tuple(links)

    def _secret(self, f: Field) -> str:
        """An input that never holds the value, with a word on whether one is set."""
        attrs = f'id="{_id(f.key)}" name="{_E(f.key)}" data-key="{_E(f.key)}"'
        is_set = self.form.effective(self.cfg, f.key) is not None
        hint = "Leave blank to keep it" if is_set else (f.hint or "")
        lock = " disabled" if f.env_value() is not None or self.locked else ""
        return (f'<input type="password" autocomplete="new-password" {attrs}{lock} '
                f'placeholder="{_E(hint, quote=True)}">')

    def _rows(self, f: Field, locked: bool) -> str:
        kind = self.form.kinds[f.kind]
        head = "".join(f"<th>{_E(label)}</th>" for _, label in kind.columns)
        lock = " disabled" if locked else ""

        def row(cells) -> str:
            tds = "".join(f'<td><input type="text" name="{_E(f.key)}.{name}" aria-label="{_E(label)}" '
                          f'value="{_E(str(v), quote=True)}"{lock}></td>'
                          for (name, label), v in zip(kind.columns, cells, strict=False))
            remove = "" if locked else '<td><button type="button" class="remove-row">Remove</button></td>'
            return f"<tr>{tds}{remove}</tr>"

        rows = "".join(row(r) for r in self.values.get(f.key, []))
        blank = row([""] * len(kind.columns))
        add = "" if locked else ('<button type="button" class="add-row">Add a row</button>'
                                 f"<template>{blank}</template>")
        marker = "" if locked else f'<input type="hidden" name="{_E(f.key)}" value="1">'
        return (f'{marker}<table class="rows" data-key="{_E(f.key)}"><thead><tr>{head}</tr></thead>'
                f"<tbody>{rows}</tbody></table>{add}")

    def _field(self, f: Field) -> str:
        kind = self.form.kinds.get(f.kind)
        env = f.env_value()
        locked = self.locked or env is not None
        secret = kind is not None and kind.secret
        if kind is not None and kind.rows:
            control = self._rows(f, locked)
        elif secret:
            control = self._secret(f)
        else:
            value = str(self.values.get(f.key, "")) if env is None else env
            control = _input(f, value, locked)
        unit = f'<span class="unit">{_E(f.unit)}</span>' if f.unit else ""
        when = f' data-when="{_E(f.when)}"' if f.when else ""
        help_text = f'<p class="help">{_E(f.help)}</p>' if f.help else ""
        lock = f'<p class="help locked">Set by {_E(f.env_name)} on the server.</p>' if env is not None else ""
        problem = self.errors.get(f.key)
        error = f'<p class="problem" id="{_id(f.key)}-problem" role="alert">{_E(problem)}</p>' if problem else ""
        label = f'<label for="{_id(f.key)}">{_E(f.label)}</label>' \
            if not (kind is not None and kind.rows) else f'<span class="label">{_E(f.label)}</span>'
        return (f'<div class="field" data-field="{_E(f.key)}"{when}>{label}'
                f'<div class="{"control stack" if kind is not None and kind.rows else "control"}">'
                f'{control}{unit}</div>{help_text}{lock}{error}</div>')

    def _group(self, g: Group) -> str:
        about = f'<p class="about">{_E(g.about)}</p>' if g.about else ""
        fields = "".join(self._field(f) for f in g.fields)
        return f"<fieldset><legend>{_E(g.heading)}</legend>{about}{fields}</fieldset>"

    def _tab(self, t: Tab) -> str:
        return (f'<section class="panel" id="{_E(t.name)}" data-tab="{_E(t.name)}">'
                f'<h2>{_E(t.title)}</h2>{"".join(self._group(g) for g in t.groups)}</section>')

    def _access(self) -> str:
        if self.login is None:
            return ""
        if not self.login.on:
            return ""
        return ('<section class="panel" id="access" data-tab="access"><h2>Access</h2>'
                '<fieldset><legend>Access token</legend><div class="field wide">'
                '<div class="control">'
                f'<input type="password" id="access-token" readonly autocomplete="off" aria-label="Access token" '
                f'value="{_E(self.login.token, quote=True)}">'
                '<button type="button" id="show-token" aria-controls="access-token">Show</button>'
                '<button type="submit" form="token-form">Replace token</button></div>'
                '<p class="help">Other apps send this to read the logs, and to install from a terminal.</p>'
                '</div></fieldset></section>')

    def render(self, banners: list[tuple[str, str]], changes: list[dict], has_backup: bool) -> str:
        banner_html = "".join(f'<p class="banner {klass}" role="alert">{_E(words)}</p>' for klass, words in banners)
        signs_in = self.login is not None and self.login.on
        tabs = "".join(f'<a href="#{_E(t.name)}" data-tab="{_E(t.name)}">{_E(t.title)}</a>' for t in self.form.tabs)
        if signs_in:
            tabs += '<a href="#access" data-tab="access">Access</a>'
        links = "".join(f'<a href="{_E(href, quote=True)}">{_E(words)}</a>' for href, words in self.links)
        if signs_in:
            links += '<form method="post" action="logout"><button type="submit">Sign out</button></form>'
        links = f'<div class="links">{links}</div>' if links else ""
        panels = "".join(self._tab(t) for t in self.form.tabs) + self._access()
        token_form = f'<form method="post" action="{self.url}/token" id="token-form"></form>' if signs_in else ""
        rows = "".join(f"<tr><td>{_E(c['name'])}</td><td>{_E(c['old'])}</td><td>{_E(c['new'])}</td></tr>"
                       for c in changes)
        listed = (f'<table id="changes"><thead><tr><th>Setting</th><th>Was</th><th>Now</th></tr></thead>'
                  f"<tbody>{rows}</tbody></table>") if changes else ""
        lock = " disabled" if self.locked else ""
        restore = f'<button type="submit" name="mode" value="restore" formnovalidate id="restore"{lock}>' \
                  "Restore the previous version</button>" if has_backup else ""
        initials = {f.key: initial(self.saved_values.get(f.key, "")) for f in self.form.fields}
        data = _json(initials)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_E(self.title)}</title>
{_stylesheets(self.url, self.styles)}
</head>
<body>
<header class="top"><h1>{_E(self.title)}</h1>{links}</header>
{banner_html}{listed}
<nav class="tabs">{tabs}</nav>
<form method="post" action="{self.url}" id="settings-form" novalidate data-url="{self.url}">
<input type="hidden" name="mode" value="form">
{panels}
<div class="savebar">
<span id="unsaved" aria-live="polite"></span>
<button type="submit" name="action" value="check" id="check">Check</button>
<button type="submit" name="action" value="save" class="primary" id="save"{lock}>Save and restart</button>
{restore}
</div>
</form>
{token_form}
<dialog id="review"><h2>Save and restart?</h2><p class="about">The server restarts on the new settings.</p>
<table><thead><tr><th>Setting</th><th>Was</th><th>Now</th></tr></thead><tbody></tbody></table>
<button type="button" id="review-cancel">Cancel</button>
<button type="button" class="primary" id="review-save">Save and restart</button></dialog>
<script type="application/json" id="initial">{data}</script>
<script src="{self.url}/assets/settings.js"></script>
</body>
</html>
"""


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def _stylesheets(url: str, styles: Iterable[str]) -> str:
    """The links to epd's look, the page's layout and then a project's own."""
    sheets = (LOOK_CSS, f"{url}/assets/settings.css", *styles)
    return "".join(f'<link rel="stylesheet" href="{_E(s, quote=True)}">' for s in sheets)


def _broken_page(problem: str, url: str, styles: Iterable[str], title: str, has_backup: bool) -> str:
    """The page for a file the form cannot read: the problem, and the way back."""
    restore = (f'<form method="post" action="{url}"><input type="hidden" name="mode" value="restore">'
               '<button type="submit" name="action" value="save">Restore the previous version</button></form>'
               ) if has_backup else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{_E(title)}</title>
{_stylesheets(url, styles)}</head>
<body><h1>{_E(title)}</h1><p class="banner problem" id="problem" role="alert">{_E(problem)}</p>{restore}</body></html>
"""


def settings_blueprint(form: Form, path: str, check: Callable[[str], None], *,
                       restart: Callable[[], None] = restart_soon, login: Login | None = None,
                       live_keys: Iterable[str] = (), take_live: Callable[[str], None] | None = None,
                       url: str = "settings", styles: Iterable[str] = (), title: str = "Settings",
                       links: Iterable[tuple[str, str]] = (), password_env: str = "",
                       ) -> Blueprint:
    """The settings page for the config file at ``path``.

    Args:
        form: the project's settings.
        check: raises ``ValueError``, with the problem, when the server would
            not start on a config's text. Give it the same test the server uses.
        restart: starts the server again on the saved file.
        login: adds an Access tab with the access token, and a Sign out button.
        live_keys: fields the server can take without a restart: a save that
            changes only these calls ``take_live`` with the new text.
        url: where the page sits, relative to the server's root, with no slash.
        styles: stylesheets to load after the page's own.
        links: other pages to link to, as ``(href, words)``.
        password_env: the variable that turns on the sign-in, for the page to
            name when no password is set.
    """
    bp = Blueprint("settings", __name__)
    live = frozenset(live_keys)
    styles = tuple(styles)

    def has_backup() -> bool:
        return os.path.exists(path + ".bak")

    def page(text: str, status: int = 200, values=None, errors=None, banners=(), changes=()) -> Response:
        try:
            view = _Page(form, text, values or {}, errors or {}, False, login, url, styles, title, links)
        except FormError as exc:
            return _no_store(_broken_page(str(exc), url, styles, title, has_backup()), status or 200)
        problems = list(banners)
        if not os.access(path, os.W_OK):
            problems.append(("problem", READ_ONLY))
            view.locked = True
        if login is not None and not login.on:
            how = f" Set {password_env} to turn on sign-in." if password_env else ""
            problems.append(("problem", f"No password is set, so anyone on the network can change these settings.{how}"))
        return _no_store(view.render(problems, list(changes), has_backup()), status)

    @bp.route(f"/{url}/assets/<name>", methods=["GET"])
    def asset(name: str):
        if name not in _ASSETS:
            abort(404)
        return send_from_directory(_ASSETS_DIR, name)

    @bp.route(f"/{url}", methods=["GET"])
    def show():
        with open(path) as f:
            text = f.read()
        doubled = twice(text, " in config.yaml on the server")
        if doubled:
            return _no_store(_broken_page(doubled, url, styles, title, has_backup()), 200)
        return page(text, banners=[("notice", SAVED)] if request.args.get("saved") else ())

    @bp.route(f"/{url}/token", methods=["POST"])
    def replace_token():
        if login is None or not login.on:
            abort(404)
        login.replace_token()
        return redirect(f"../{url}", 303)

    @bp.route(f"/{url}", methods=["POST"])
    def change():
        posted = request.form
        wants_json = posted.get("action") == "review" or "application/json" in request.headers.get("Accept", "")
        with open(path) as f:
            current = f.read()
        values = {f.key: v for f, v in
                  ((form.by_key[k], v) for k, v in form.submitted(posted).items())
                  if not (form.kinds.get(f.kind) and form.kinds[f.kind].secret)}
        try:
            out = save_flow(form, path, posted, check, restart=restart, live_keys=live, take_live=take_live)
        except ValueError:
            abort(400)

        if out.state == "refused":
            if wants_json:
                at = {"field": out.key, "error": out.errors.get(out.key)} if out.key else {}
                return jsonify(problem=out.problem, **at), out.status
            return page(current, out.status, values, out.errors, [("problem", out.problem)])
        if out.state == "review":
            return jsonify(changes=out.changes, same=out.same)
        if out.state == "checked":
            if out.same:
                return page(current, 200, values, banners=[("notice", NOTHING)])
            return page(current, 200, values, banners=[("notice", NO_PROBLEMS)], changes=out.changes)
        if out.state == "same":
            if wants_json:
                return jsonify(saved=False, same=True)
            return page(current, 200, values, banners=[("notice", NOTHING)])
        if out.state == "live":
            if wants_json:
                return jsonify(saved=True, restarted=False)
            return redirect(f"{url}?saved=1", 303)
        if wants_json:
            return jsonify(saved=True, restarted=True)
        return _no_store(_restarting_page(url, styles, title))

    return bp


def _restarting_page(url: str, styles: Iterable[str], title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="5;url={url}?saved=1">
<title>{_E(title)}</title>{_stylesheets(url, styles)}</head>
<body><h1>{_E(title)}</h1><p class="banner notice" id="restarting">Saved. The server is restarting.</p></body></html>
"""


def _no_store(body: str, status: int = 200) -> Response:
    rsp = make_response(body, status)
    rsp.headers["Cache-Control"] = "no-store"
    return rsp
