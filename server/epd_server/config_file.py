"""config.yaml as text: read as the server reads it, and edited with its comments kept.

The file is edited with ruamel.yaml, which keeps its comments and layout, and
read with PyYAML, which is what a server starts on. The two read some plain
scalars differently (``1:00`` is a string to ruamel and a number to PyYAML),
so a string is written in quotes whenever PyYAML would read it as something
else. Check every edit by reading it back: :func:`changed_paths` and
:func:`reads_as` say what it did.
"""
from __future__ import annotations

import io
import re
from collections.abc import Iterable
from typing import Any

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import CommentMark
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
from ruamel.yaml.tokens import CommentToken

# A key the file does not have.
MISSING: Any = object()


class FormError(ValueError):
    """The file cannot take this edit. The message says to edit config.yaml on the server."""


# What to say of a file only a hand edit on the server can fix.
NOT_YAML = "config.yaml is not valid YAML. Fix it on the server."
NOT_A_MAPPING = "config.yaml has no settings at its top level. Fix it on the server."
EDIT_ON_SERVER = "Edit config.yaml on the server."
ON_SERVER = " in config.yaml on the server"

_HHMMSS = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def read(text: str) -> dict:
    """``text`` as the server reads it.

    Raises:
        FormError: it is not YAML, or not a mapping.
    """
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError:
        raise FormError(NOT_YAML)
    if cfg is None:
        return {}
    if not isinstance(cfg, dict):
        raise FormError(NOT_A_MAPPING)
    return cfg


_DUPLICATE = re.compile(r'found duplicate key "(.*?)" with value')


def twice(text: str, where: str = "") -> str | None:
    """What to say when ``text`` writes a key twice in one mapping, or None.

    PyYAML, and so the server, takes the second copy and drops the first
    without a word, so the person must choose which one to keep.
    """
    try:
        YAML().load(text)
    except DuplicateKeyError as exc:
        return _twice_words(exc, text.splitlines(), where)
    except Exception:  # noqa: BLE001 - any other fault is the YAML check's to report
        return None
    return None


def _twice_words(exc: DuplicateKeyError, lines: list[str], where: str) -> str:
    match = _DUPLICATE.search(exc.problem or "")
    key = match.group(1) if match else "A key"
    second = exc.problem_mark.line + 1
    first = _first_copy(lines, key, exc.problem_mark.line, exc.problem_mark.column)
    at = f"on lines {first} and {second}" if first else f"the second time on line {second}"
    return f"{key} appears twice, {at}. Delete one{where}: the server uses line {second}."


def _first_copy(lines: list[str], key: str, line: int, column: int) -> int | None:
    """The 1-based line of ``key``'s first copy in the mapping whose second
    copy is at ``line`` and ``column``, as far as block style shows it."""
    copy = re.compile(r"""["']?""" + re.escape(key) + r"""["']?\s*:""")
    for n in range(line - 1, -1, -1):
        text = lines[n]
        body = text.lstrip(" -")
        if not body or body.startswith("#"):
            continue
        at = len(text) - len(body)
        if at < column:
            return None
        if at == column and copy.match(body):
            return n + 1
    return None


def lookup(cfg: Any, path: Iterable) -> Any:
    node = cfg
    for k in path:
        if not isinstance(node, dict) or k not in node:
            return MISSING
        node = node[k]
    return node


def same(a: Any, b: Any) -> bool:
    """Whether the file's value ``a`` already says ``b``: a number is not the
    string of its digits, nor is true 1."""
    if a is MISSING:
        return False
    return (isinstance(a, bool) == isinstance(b, bool) and isinstance(a, str) == isinstance(b, str)
            and a == b)


def _plain(s: str) -> bool:
    """Whether PyYAML reads ``s``, unquoted, as the same string. A time of
    day is quoted anyway: 1:00 unquoted is a number of minutes."""
    if _HHMMSS.fullmatch(s):
        return False
    try:
        return yaml.safe_load(s) == s
    except yaml.YAMLError:
        return False


def _node(value: Any) -> Any:
    """``value`` as ruamel writes it: strings quoted when they must be, lists
    on one line, mappings as blocks, and a list of mappings one to a line."""
    if isinstance(value, str):
        return value if _plain(value) else DoubleQuotedScalarString(value)
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        seq = CommentedSeq()
        for v in value:
            item = CommentedMap((_node(k), _node(x)) for k, x in v.items())
            # One that holds a list of mappings, as a group of days holds its
            # ranges, is a block, so those stay one to a line.
            if not any(_is_mapping_list(x) for x in v.values()):
                item.fa.set_flow_style()
            seq.append(item)
        return seq
    if isinstance(value, list):
        seq = CommentedSeq(_node(v) for v in value)
        seq.fa.set_flow_style()
        return seq
    if isinstance(value, dict):
        m = CommentedMap((_node(k), _node(v)) for k, v in value.items())
        if not value:
            m.fa.set_flow_style()
        return m
    return value


def _is_mapping_list(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, dict) for x in v)


def _is_block(v: Any) -> bool:
    return isinstance(v, CommentedMap) and len(v) > 0 and not v.fa.flow_style()


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


# ruamel keeps the comment after a key as one token: the rest of the key's
# line, then every line up to the next key. A key with a block mapping under
# it has its token on its own line, and the lines after the block hang off
# the block's last key. These helpers move those lines when a key comes or
# goes, so a comment stays beside what it describes.

def _end(m: CommentedMap, key: Any) -> tuple[CommentedMap, Any]:
    """The mapping and key whose token holds the lines after ``m[key]`` and all under it."""
    while _is_block(m[key]):
        m = m[key]
        key = next(reversed(m))
    return m, key


def _after(m: CommentedMap, key: Any) -> str:
    item = m.ca.items.get(key)
    tok = item[2] if item and len(item) > 2 else None
    return tok.value.partition("\n")[2] if tok is not None else ""


def _set_after(m: CommentedMap, key: Any, lines: str) -> None:
    item = m.ca.items.get(key)
    tok = item[2] if item and len(item) > 2 else None
    if tok is not None:
        tok.value = tok.value.partition("\n")[0] + "\n" + lines
    elif lines:
        m.ca.items.setdefault(key, [None, None, None, None])[2] = CommentToken(
            "\n" + lines, CommentMark(0), None)


def _split(lines: str, indent: int) -> tuple[str, str]:
    """``lines`` in two at the first blank line or the first one indented
    less than ``indent``: what belongs with the entry, and what comes after
    the mapping it is in."""
    parts = lines.splitlines(keepends=True)
    for i, line in enumerate(parts):
        if not line.strip() or _indent_of(line) < indent:
            return "".join(parts[:i]), "".join(parts[i:])
    return lines, ""


def _outside(lines: str, indent: int) -> str:
    """The lines that outlive an entry at ``indent``: blanks, and comments no deeper than it."""
    return "".join(ln for ln in lines.splitlines(keepends=True)
                   if not ln.strip() or _indent_of(ln) <= indent)


def _join(a: str, b: str) -> str:
    """``a`` then ``b``, without adding to the blank lines where they meet."""
    head, tail = a.splitlines(keepends=True), b.splitlines(keepends=True)
    while head and tail and not head[-1].strip() and not tail[0].strip():
        tail.pop(0)
    return "".join(head + tail)


def _yaml(indent: int = 2, offset: int = 0) -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=indent, sequence=indent + offset, offset=offset)
    return y


_KEY_LINE = re.compile(r"( *)[^ #\-][^:#]*:(\s|$)")
_DASH_LINE = re.compile(r"( *)- ")


def _indents(text: str) -> tuple[int, int]:
    """How far ``text`` indents a mapping under its key, and a list's dash
    past its key: 2 and 2 when the file has no example of either.

    ruamel's own guess takes both from the first list it meets, which says
    nothing of how the mappings are indented."""
    mapping, offset, key_at = None, None, None
    for line in text.splitlines():
        key, dash = _KEY_LINE.match(line), _DASH_LINE.match(line)
        if key:
            at = len(key[1])
            if key_at is not None and at > key_at and mapping is None:
                mapping = at - key_at
            key_at = at
        elif dash and key_at is not None and offset is None:
            offset = len(dash[1]) - key_at
    return mapping or 2, offset if offset is not None and offset >= 0 else 2


class Doc:
    """config.yaml as ruamel holds it, with edits that keep its comments."""

    def __init__(self, text: str):
        self.marker = text.startswith("---")
        if text.strip():
            self.ind, self.offset = _indents(text)
            try:
                root = _yaml(self.ind, self.offset).load(text)
            except DuplicateKeyError as exc:
                raise FormError(_twice_words(exc, text.splitlines(), ON_SERVER)) from None
            except Exception:  # noqa: BLE001 - any ruamel failure means the form cannot edit it
                raise FormError(NOT_YAML) from None
        else:
            root, self.ind, self.offset = None, 2, 2
        if root is None:
            root = CommentedMap()
        if not isinstance(root, CommentedMap):
            raise FormError(NOT_A_MAPPING)
        self.root = root

    def text(self) -> str:
        out = io.StringIO()
        y = _yaml(self.ind, self.offset)
        y.explicit_start = self.marker
        y.dump(self.root, out)
        return out.getvalue()

    def _chain(self, path) -> list[tuple[CommentedMap, int]]:
        """The mappings along ``path``'s parents with their depths, as far as they go."""
        chain = [(self.root, 0)]
        for depth, k in enumerate(path[:-1], start=1):
            v = chain[-1][0].get(k)
            if not isinstance(v, CommentedMap):
                break
            chain.append((v, depth))
        return chain

    def get(self, path) -> Any:
        return lookup(self.root, path)

    def set(self, path, value: Any) -> None:
        node = _node(value)
        m, depth = self.root, 0
        unflowed = None
        for i, k in enumerate(path[:-1]):
            v = m.get(k)
            if isinstance(v, CommentedMap):
                if v.fa.flow_style():
                    # {} becoming a block: the lines after its key go after the block.
                    unflowed = (m, k, _after(m, k))
                    _set_after(m, k, "")
                    v.fa.set_block_style()
                m, depth = v, depth + 1
                continue
            for j in reversed(path[i + 1:]):
                node = CommentedMap([(_node(j), node)])
            path = path[:i + 1]
            break
        key = path[-1]
        if key in m:
            self._replace(m, depth, key, node)
        else:
            self._append(m, depth, _node(key), node)
        if unflowed:
            um, uk, lines = unflowed
            em, ek = _end(um, uk)
            _set_after(em, ek, _after(em, ek) + lines)

    def _append(self, m: CommentedMap, depth: int, key: Any, node: Any) -> None:
        moved = ""
        if len(m):
            em, ek = _end(m, next(reversed(m)))
            keep, moved = _split(_after(em, ek), self.ind * depth)
            if depth == 0:
                keep += "\n"
            _set_after(em, ek, keep)
        m.ca.items.pop(key, None)
        m[key] = node
        if moved:
            em, ek = _end(m, key)
            _set_after(em, ek, _after(em, ek) + moved)

    def _replace(self, m: CommentedMap, depth: int, key: Any, node: Any) -> None:
        if not _is_block(m[key]) and not _is_block(node):
            m[key] = node
            return
        em, ek = _end(m, key)
        lines = _after(em, ek)
        if _is_block(m[key]):
            lines = _outside(lines, self.ind * depth)
            _set_after(m, key, "")
        _set_after(em, ek, "")
        m[key] = node
        em, ek = _end(m, key)
        _set_after(em, ek, _after(em, ek) + lines)

    def _delete(self, m: CommentedMap, depth: int, key: Any, carried: str = "") -> str:
        """Take ``key`` out of ``m``. The lines after it move to the entry
        before it; with none before it, they are handed back."""
        keys = list(m)
        i = keys.index(key)
        em, ek = _end(m, key)
        own = _after(m, key) if em is not m else ""
        lines = _outside(own + _after(em, ek) + carried, self.ind * depth)
        del m[key]
        m.ca.items.pop(key, None)
        if i > 0 and lines:
            pm, pk = _end(m, keys[i - 1])
            _set_after(pm, pk, _join(_after(pm, pk), lines))
            return ""
        return lines

    def remove(self, path) -> bool:
        """Take the key at ``path`` out, and any mapping that leaves empty."""
        chain = self._chain(path)
        if len(chain) < len(path):
            return False
        m, depth = chain[-1]
        if path[-1] not in m:
            return False
        carried = self._delete(m, depth, path[-1])
        level = len(path) - 1
        while level > 0 and not len(chain[level][0]):
            parent, pdepth = chain[level - 1]
            carried = self._delete(parent, pdepth, path[level - 1], carried)
            level -= 1
        if carried and level > 0:
            parent = chain[level - 1][0]
            _set_after(parent, path[level - 1], _join(_after(parent, path[level - 1]), carried))
        return True

    def set_pools(self, pools: dict[str, list[str]]) -> None:
        pm = self.get(("display", "pools"))
        if not isinstance(pm, CommentedMap) or not len(pm):
            self.set(("display", "pools"), pools)
            return
        if pm.fa.flow_style():
            pm.fa.set_block_style()
        keys = {str(k): k for k in pm}
        for name, images in pools.items():
            if name not in keys:
                self._append(pm, 2, _node(name), _node(images))
                keys[name] = name
            elif isinstance(pm[keys[name]], CommentedSeq):
                if list(pm[keys[name]]) != images:
                    pm[keys[name]][:] = [_node(i) for i in images]
            else:
                self._replace(pm, 2, keys[name], _node(images))
        for name, k in list(keys.items()):
            if name not in pools:
                self.remove(("display", "pools", k))
                del keys[name]
        if [str(k) for k in pm] != list(pools):
            em, ek = _end(pm, next(reversed(pm)))
            keep, moved = _split(_after(em, ek), self.ind * 2)
            _set_after(em, ek, keep)
            for name in pools:
                pm.move_to_end(keys[name])
            em, ek = _end(pm, next(reversed(pm)))
            _set_after(em, ek, _after(em, ek) + moved)


def flat(d: Any, prefix: tuple = ()) -> dict[tuple, Any]:
    if not isinstance(d, dict) or (not d and prefix):
        return {prefix: d}
    out: dict[tuple, Any] = {}
    for k, v in d.items():
        out.update(flat(v, prefix + (str(k),)))
    return out


def changed_paths(old: dict, new: dict) -> list[tuple]:
    a, b = flat(old), flat(new)
    return [p for p in dict.fromkeys([*a, *b])
            if not (p in a and p in b and same(a[p], b[p]))]


def reads_as(got: Any, value: Any) -> bool:
    if value is MISSING:
        return got is MISSING
    if isinstance(value, dict):
        return (isinstance(got, dict) and [str(k) for k in got] == list(value)
                and not changed_paths(got, value))
    return same(got, value)
