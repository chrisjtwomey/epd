"""A settings form over config.yaml: its tabs and fields, what a filled-in form
does to the file, and the changes in words.

A project lists its settings as :class:`Tab`, :class:`Group` and :class:`Field`,
and makes one :class:`Form`. A field of a kind this module does not know brings
a :class:`Kind`. Every edit goes through :mod:`epd_server.config_file`, and is
read back with PyYAML before it is accepted.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config_file import (EDIT_ON_SERVER, MISSING, Doc, FormError, changed_paths, flat, lookup, read,
                          reads_as, same)


def host_zone() -> str:
    """The zone the server runs in when config.yaml names none."""
    tz = datetime.now().astimezone().tzinfo
    return str(getattr(tz, "key", "") or (tz.tzname(None) if tz else "") or "UTC")


@dataclass(frozen=True)
class Field:
    """One setting on the form.

    ``default`` is what the server takes when the key is absent, or a function
    of the config that gives it; the form shows it as the field's value.
    ``hint`` is an example of the value, for a field with no default. ``when``
    is another field and a
    value, as ``source.kind=store``, or values, as ``log.level=info|debug``:
    the field shows only while that one holds one of them. ``env`` is false for keys the server reads without looking for an
    environment variable. ``recommended`` is the value to keep, which the
    group's drawing marks; below it, ``caution`` shows under the field. With
    ``zero_means_always``, 0 is not below it: the fan's 0 keeps it on.
    ``refused`` is what the field says when the server's check refuses its
    value, in place of the check's own words, which name config keys.
    """
    key: str
    label: str
    help: str = ""
    kind: str = "text"      # text password zone int number bool choice stops time order pools, or a Form's own
    default: Any = None
    hint: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: int = 1
    when: str = ""
    env: bool = True
    long: str = ""          # the name in messages, when the label leans on its place on the page
    scale: int = 1          # the file's units in one of the input's: 60 shows seconds as minutes
    recommended: float | None = None
    caution: str = ""
    zero_means_always: bool = False
    refused: str = ""

    def cautions(self, value: Any) -> bool:
        """Whether ``value``, as the form or the file holds it, is below the recommended one."""
        if self.recommended is None:
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        return v < self.recommended and not (v == 0 and self.zero_means_always)

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(self.key.split("."))

    @property
    def env_name(self) -> str:
        return "_".join(self.path).upper()


    def env_value(self) -> str | None:
        """The environment variable that sets this key over the file, if one is set."""
        return os.environ.get(self.env_name) if self.env else None


@dataclass(frozen=True)
class Group:
    """Fields under one heading. ``store``, ``action``, ``visual`` and
    ``caption`` name what a project's page draws beside them; this module does
    not read them. ``about`` is the line under the heading."""
    heading: str
    fields: tuple[Field, ...]
    store: str = ""
    action: str = ""
    visual: str = ""
    caption: str = ""
    about: str = ""


@dataclass(frozen=True)
class Tab:
    """``sheet`` sets the tab out as a spec sheet: each group under a rule,
    its heading in a column beside it, and each field a line with a dotted
    leader from its name to its value."""
    name: str
    title: str
    groups: tuple[Group, ...]
    sheet: bool = False

    @property
    def fields(self) -> list[Field]:
        return [f for g in self.groups for f in g.fields]


class FieldError(ValueError):
    """A value the form cannot write. The message is for the person filling it in."""


@dataclass
class Edit:
    """What a posted form does to config.yaml."""
    text: str
    errors: dict[str, str]      # a field's key, and what is wrong with its value
    changed: list[str]          # the fields it changes


def default_of(f: Field, cfg: dict) -> Any:
    """What the server takes for ``f`` when config.yaml leaves it out."""
    return f.default(cfg) if callable(f.default) else f.default


def scaled(f: Field, value: Any) -> Any:
    """``value`` from the file in the input's units."""
    if f.scale == 1 or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    shown = value / f.scale
    return int(shown) if shown == int(shown) else shown


def as_input(value: Any) -> str:
    """A value as an input shows it."""
    if value is None or value is MISSING:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def input_text(f: Field, value: Any) -> str:
    """A value from the file as ``f``'s input shows it."""
    return as_input(scaled(f, value))


def initial(value: Any) -> str:
    """A value as a page compares it, to tell whether the field has changed."""
    if isinstance(value, list):
        return json.dumps([list(r) for r in value], separators=(",", ":"), ensure_ascii=False)
    return value


def words_of(v: Any) -> str:
    """A value in the words of a list of changes."""
    if v is MISSING:
        return "not set"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if v == {}:
        return "off"
    return str(v)


_HHMM = re.compile(r"(\d{1,2}):(\d{2})")


def clock_time(raw: str) -> str | None:
    """``raw`` as HH:MM, or None when it is not a time of day."""
    m = _HHMM.fullmatch(raw)
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        return None
    return f"{int(m[1]):02d}:{m[2]}"


def _either(words) -> str:
    """"A or B", "A, B or C": the choices as a person lists them."""
    words = list(words)
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def _bounds(f: Field, v: float) -> None:
    if f.minimum is not None and v < f.minimum:
        raise FieldError(f"Enter {f.minimum:g} or more.")
    if f.maximum is not None and v > f.maximum:
        raise FieldError(f"Enter {f.maximum:g} or less.")
    if f.step > 1 and v % f.step:
        raise FieldError(f"Enter a multiple of {f.step}.")


def _images(pages: str) -> list[str]:
    return [p.strip() for p in pages.split(",") if p.strip()]


class Writer:
    """What a :class:`Kind` writes through while a form is applied."""

    def __init__(self, cfg: dict, doc: Doc):
        self.cfg = cfg
        self.doc = doc
        self.changed: list[str] = []
        self.errors: dict[str, str] = {}
        self.expect: dict[tuple, Any] = {}

    def put(self, path, value: Any) -> None:
        """Set ``path``, and check after that the file reads back with it."""
        self.doc.set(path, value)
        self.expect[tuple(path)] = value


def write_value(w: Writer, f: Field, value: Any) -> None:
    """Write one value: None takes the key out, and a value the server already
    takes for the key changes nothing."""
    cur = lookup(w.cfg, f.path)
    if value is None:
        if cur is not MISSING and cur != "" and w.doc.remove(f.path):
            w.changed.append(f.key)
            w.expect[f.path] = MISSING
    elif not same(cur, value) and not (cur is MISSING and same(default_of(f, w.cfg), value)):
        w.put(f.path, value)
        w.changed.append(f.key)


class Kind:
    """A kind of field a :class:`Form` does not know: how it shows, posts, parses
    and writes. With ``rows``, its value is several inputs rather than one."""
    rows = False
    #: What a list of changes says when the file has no value.
    when_missing: str | None = None

    def show(self, f: Field, value: Any, cfg: dict) -> Any:
        """What the input shows, for ``value`` from the file or MISSING."""
        return as_input(scaled(f, default_of(f, cfg) if value is MISSING else value))

    def submitted(self, form, key: str) -> Any:
        """The value a posted form holds, as :meth:`show` gives it."""
        return form.getlist(key)[-1]

    def parse(self, f: Field, raw: Any) -> Any:
        """The value to write for what the input holds.

        Raises:
            FieldError: the person must change it.
        """
        return raw

    def write(self, w: Writer, f: Field, value: Any) -> None:
        """Change the file, and add ``f.key`` to ``w.changed`` if it changed."""
        write_value(w, f, value)


def _normal_pools(v: Any) -> list[tuple[str, list]]:
    if not isinstance(v, dict):
        return []
    return [(str(n), p if isinstance(p, list) else [p]) for n, p in v.items()]


class Pools(Kind):
    """``display.pools``: rows of a set's name and its pages."""
    rows = True
    when_missing = "none"

    def show(self, f, value, cfg):
        if not isinstance(value, dict):
            return []
        return [(str(n), ", ".join(map(str, p if isinstance(p, list) else [p]))) for n, p in value.items()]

    def submitted(self, form, key):
        return list(zip(form.getlist(key + ".name"), form.getlist(key + ".pages"), strict=False))

    def parse(self, f, raw):
        pools: dict[str, list[str]] = {}
        for name, pages in raw:
            name, images = name.strip(), _images(pages)
            if not name and not images:
                continue
            if not name:
                raise FieldError("Each set needs a name.")
            if name in pools:
                raise FieldError(f"Two sets are named {name}. Rename one.")
            if not images:
                raise FieldError(f"{name} has no pages. Add one.")
            pools[name] = images
        return pools

    def write(self, w, f, value):
        if not value:
            if lookup(w.cfg, f.path) is not MISSING:
                w.errors[f.key] = "Add at least one pool."
            return
        if _normal_pools(lookup(w.cfg, f.path)) != list(value.items()):
            w.doc.set_pools(value)
            w.expect[f.path] = value
            w.changed.append(f.key)


class Form:
    """A project's settings, as one form.

    Args:
        tabs: the settings, in the page's order.
        extra: fields outside the tabs, such as those on an install page.
        extra_title: what a list of changes names ``extra`` by.
        kinds: this project's own kinds of field, by name.
        joint: a field's key, and what writes it and the fields under it
            together: it takes the file, every parsed value and a ``put``, and
            gives the keys it changed.
        with_words: gives the file with a setting whose value a list of changes
            should read as one line, such as a schedule, in words.
    """

    def __init__(self, tabs: Iterable[Tab], extra: Iterable[Field] = (), extra_title: str = "",
                 kinds: Mapping[str, Kind] | None = None,
                 joint: Mapping[str, Callable[[dict, dict, Callable], list[str]]] | None = None,
                 with_words: Callable[[dict], dict] | None = None):
        self.tabs = tuple(tabs)
        self.extra = tuple(extra)
        self.extra_title = extra_title
        self.kinds = {"pools": Pools(), **(kinds or {})}
        self.joint = dict(joint or {})
        self.with_words = with_words or (lambda cfg: cfg)
        self.fields: tuple[Field, ...] = tuple(f for t in self.tabs for f in t.fields) + self.extra
        self.by_key: dict[str, Field] = {f.key: f for f in self.fields}
        self.tab_of: dict[str, str] = {f.key: t.name for t in self.tabs for f in t.fields}

    def effective(self, cfg: dict, key: str) -> Any:
        """The value the server uses for ``key``: the file's, or the default."""
        v = lookup(cfg, self.by_key[key].path)
        return default_of(self.by_key[key], cfg) if v is MISSING else v

    def rows(self, f: Field) -> bool:
        """Whether ``f`` is rows of inputs rather than one."""
        kind = self.kinds.get(f.kind)
        return kind is not None and kind.rows

    def shown(self, cfg: dict) -> dict[str, Any]:
        """Each field's value as its input shows it: a string, or a kind's rows."""
        out: dict[str, Any] = {}
        for f in self.fields:
            v = lookup(cfg, f.path)
            kind = self.kinds.get(f.kind)
            out[f.key] = kind.show(f, v, cfg) if kind else \
                as_input(scaled(f, default_of(f, cfg) if v is MISSING else v))
        return out

    def defaults(self, cfg: dict) -> dict[str, str]:
        """Each field's default as its input shows it, for the fields that have one."""
        out: dict[str, str] = {}
        for f in self.fields:
            if self.rows(f):
                continue
            d = default_of(f, cfg)
            if d is not None:
                out[f.key] = as_input(scaled(f, d))
        return out

    def submitted(self, form) -> dict[str, Any]:
        """The values a posted form holds, as :meth:`shown` gives them."""
        out: dict[str, Any] = {}
        for f in self.fields:
            if f.key not in form:
                continue
            kind = self.kinds.get(f.kind)
            out[f.key] = kind.submitted(form, f.key) if kind else form.getlist(f.key)[-1]
        return out

    def parse(self, f: Field, raw: Any) -> Any:
        """The value to write for what the input holds; None takes the key out,
        so the server uses its default."""
        kind = self.kinds.get(f.kind)
        if kind is not None:
            return kind.parse(f, raw)
        entered = str(raw)
        raw = entered.strip()
        if f.kind == "bool":
            return raw == "true"
        if raw == "":
            return None
        if f.kind == "password":
            return entered
        if f.kind == "int":
            try:
                v = int(raw)
            except ValueError:
                raise FieldError("Enter a whole number.") from None
            _bounds(f, v)
            return v * f.scale
        if f.kind == "number":
            try:
                v = int(raw)
            except ValueError:
                try:
                    v = float(raw)
                except ValueError:
                    raise FieldError("Enter a number.") from None
                if not math.isfinite(v):
                    raise FieldError("Enter a number.")
            _bounds(f, v)
            return v
        if f.kind in ("choice", "stops"):
            if raw not in [c for c, _ in f.choices]:
                raise FieldError("Choose " + _either(w for _, w in f.choices) + ".")
            return int(raw) if raw.isdigit() else raw
        if f.kind == "time":
            at = clock_time(raw)
            if at is None:
                raise FieldError("Enter a time as HH:MM.")
            return at
        if f.kind == "order":
            return _images(raw)
        return raw

    def _is_joint(self, f: Field) -> bool:
        return any(f.key == k or f.key.startswith(k + ".") for k in self.joint)

    def apply(self, text: str, form) -> Edit:
        """config.yaml as ``text`` with the values ``form`` posts, and what they change.

        A field the form leaves out stays as it is, and so does one an
        environment variable sets. An empty field takes its key out, unless the
        file holds the key empty already.

        Raises:
            FormError: the file cannot be edited this way, or the edit would not
                read back as the form gave it.
        """
        cfg = read(text)
        rows = self.submitted(form)
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for f in self.fields:
            if f.key not in form or f.env_value() is not None:
                continue
            raw = rows[f.key] if self.rows(f) else form.getlist(f.key)[-1]
            try:
                values[f.key] = self.parse(f, raw)
            except FieldError as exc:
                errors[f.key] = str(exc)
        if errors:
            return Edit(text, errors, [])

        w = Writer(cfg, Doc(text))
        for f in self.fields:
            if f.key not in values or self._is_joint(f):
                continue
            kind = self.kinds.get(f.kind)
            write = kind.write if kind else write_value
            write(w, f, values[f.key])

        if w.errors:
            return Edit(text, w.errors, [])
        for key, write in self.joint.items():
            if key in values:
                w.changed += write(cfg, values, w.put)
        if not w.changed:
            return Edit(text, {}, [])
        new_text = w.doc.text()
        self._check_reads_back(cfg, new_text, w.changed, w.expect)
        return Edit(new_text, {}, w.changed)

    def _check_reads_back(self, cfg: dict, text: str, changed: list[str], expect: dict) -> None:
        """Refuse an edit that PyYAML would not read as the form gave it, or
        that touched a key the form did not change."""
        new = read(text)
        allowed = [tuple(k.split(".")) for k in changed]
        for path in changed_paths(cfg, new):
            if not any(path[:len(p)] == p or p[:len(path)] == path for p in allowed):
                raise FormError(f"This edit also changes {self.name_of(path)}. {EDIT_ON_SERVER}")
        for path, value in expect.items():
            if not reads_as(lookup(new, path), value):
                raise FormError(f"The form cannot save {self.name_of(path)} as entered. {EDIT_ON_SERVER}")

    def field_at(self, path: tuple) -> Field | None:
        """The field that holds ``path``, or holds the mapping it is in."""
        best = None
        for f in self.fields:
            if path[:len(f.path)] == f.path and (best is None or len(f.path) > len(best.path)):
                best = f
        return best

    def locate(self, message: str) -> tuple[str | None, str | None]:
        """The field and the tab a problem from the server's check is about, as
        far as the key it starts with says."""
        head = tuple(message.split(" ", 1)[0].rstrip(":,.").split("."))
        f = self.field_at(head)
        if f is not None:
            return f.key, self.tab_of.get(f.key)
        for n in range(len(head), 0, -1):
            for t in self.tabs:
                if any(f.path[:n] == head[:n] for f in t.fields):
                    return None, t.name
        return None, None

    def name_of(self, path: tuple) -> str:
        """A setting's name as a person finds it on the page."""
        f = self.field_at(path)
        if f is None:
            return ".".join(path)
        if f.key not in self.tab_of:
            return " · ".join([self.extra_title, f.label, *path[len(f.path):]])
        tab = next(t for t in self.tabs if t.name == self.tab_of[f.key])
        group = next(g for g in tab.groups if f in g.fields)
        name = f.long or f.label
        shared = sum((o.long or o.label) == name for o in tab.fields) > 1
        rest = path[len(f.path):]
        return " · ".join([tab.title, *([group.heading] if shared else []), name, *rest])

    def _differences(self, old: dict, new: dict) -> list[tuple[tuple, Field | None, Any, Any]]:
        """Each setting that differs from ``old`` to ``new``, in the form's order:
        its path, its field, and both values as the words take them."""
        old, new = self.with_words(old), self.with_words(new)
        a, b = flat(old), flat(new)
        order = {f.key: i for i, f in enumerate(self.fields)}
        out = []
        for path in changed_paths(old, new):
            f = self.field_at(path)
            before, after = a.get(path, MISSING), b.get(path, MISSING)
            kind = self.kinds.get(f.kind) if f is not None else None
            if kind is not None and kind.when_missing is not None:
                before = kind.when_missing if before is MISSING else before
                after = kind.when_missing if after is MISSING else after
            if f is not None and f.scale != 1:
                before, after = (_unit_words(f, v) for v in (before, after))
            if f is not None and f.kind == "stops":
                before, after = (dict(f.choices).get(str(v), v) for v in (before, after))
            out.append((order.get(f.key, len(order)) if f else len(order), path, f, before, after))
        return [(path, f, before, after) for _, path, f, before, after in
                sorted(out, key=lambda x: x[0])]

    def changes(self, old: dict, new: dict) -> list[dict[str, str]]:
        """Each setting that differs from ``old`` to ``new``, in words, in the form's order."""
        return [{"name": self.name_of(path), "old": words_of(before), "new": words_of(after)}
                for path, _, before, after in self._differences(old, new)]

    def in_use(self, running: dict, saved: dict) -> dict[str, str]:
        """Each field whose value in ``running`` differs from ``saved``, keyed by
        the field: the running value in words, with its unit, as "4.0 °C"."""
        out = {}
        for _, f, before, _ in self._differences(running, saved):
            if f is None:
                continue
            words = dict(f.choices).get(str(before)) if f.kind == "choice" else None
            words = words or words_of(before)
            if f.unit and f.scale == 1 and f.kind in ("int", "number"):
                words += f.unit if f.unit == "%" else f" {f.unit}"
            out[f.key] = words[:1].upper() + words[1:]
        return out


def _unit_words(f: Field, v: Any) -> Any:
    """A scaled field's value in the input's units, with them, as "5 minutes"."""
    shown = scaled(f, v)
    return f"{shown} {f.unit}" if shown is not v else v
