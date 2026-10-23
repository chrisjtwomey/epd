"""Board keys: a key each board shares with the server, agreed over the air
and approved by a person, and the signatures made with it.

A board with no key sends its half of an ECDH exchange (P-256, an
uncompressed point) to ``POST /pair``. The server answers with its own half,
and both derive the key with HKDF-SHA256: no salt, and ``epd board key
<device>`` as the info. The server keeps the key as pending until a person
approves it; until then the board's posts are refused, and it keeps them.

The signatures follow RFC 9421 with hmac-sha256, under the label ``sig1``,
with the body's SHA-256 as a Content-Digest (RFC 9530):

- a board signs each POST over ``"@method" "@path" "@query"
  "content-digest"``;
- the server signs its answer to the firmware image and to the routes a
  project names, over ``"@status" "content-digest"`` and the request's
  ``"@method";req "@path";req "@query";req``, so that no answer can stand in
  for another; an answer to a POST also covers the request's
  ``"content-digest";req``, so that it answers that post alone.

Both carry ``created`` and the key's id, and are good for WINDOW_S either
side of the reader's clock. The server takes each request signature once.

A board that holds a key pairs again only on a ``pair`` refusal signed with
that key, so that a device answering in the server's place cannot make it
take a key of the device's own. The server keeps the keys a board stops
using, rejected, forgotten or replaced, but takes no post under them: a post
signed with one is told to pair, under that key, and a board still on one
gets its answers signed with it until it pairs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger(__name__)

WINDOW_S = 300
LABEL = "sig1"
REQUEST_COMPONENTS = ('"@method"', '"@path"', '"@query"', '"content-digest"')
ANSWER_COMPONENTS = ('"@status"', '"content-digest"', '"@method";req', '"@path";req',
                     '"@query";req')
POST_ANSWER_COMPONENTS = (*ANSWER_COMPONENTS, '"content-digest";req')
# The keys of each board kept after it stops using them, newest first.
RETIRED_KEPT = 4

# Why a board's post was refused, for the board to act on: pair, wait for
# the approval, take the server's clock, or try again later.
PAIR = "pair"
PENDING = "pending"
CLOCK = "clock"
REFUSED = "refused"

_INPUT = re.compile(r'sig1=\("@method" "@path" "@query" "content-digest"\)'
                    r';created=(\d{1,12});keyid="([0-9a-f]{16})"')
_SIGNATURE = re.compile(r"sig1=:([A-Za-z0-9+/]{43}=):")


# ── The signature itself ────────────────────────────────────────────

def content_digest(body: bytes) -> str:
    """The Content-Digest field of ``body``: its SHA-256, as RFC 9530 writes it."""
    return "sha-256=:" + base64.b64encode(hashlib.sha256(body).digest()).decode() + ":"


def signature_params(components: Iterable[str], created: int, keyid: str) -> str:
    return "(" + " ".join(components) + f');created={created};keyid="{keyid}"'


def signature_base(lines: Iterable[tuple[str, str]], params: str) -> str:
    """The text RFC 9421 signs: each component as ``identifier: value`` on a
    line of its own, then the signature's parameters."""
    out = [f"{name}: {value}" for name, value in lines]
    out.append(f'"@signature-params": {params}')
    return "\n".join(out)


def hmac_sha256(key: bytes, base: str) -> str:
    return base64.b64encode(hmac.new(key, base.encode(), hashlib.sha256).digest()).decode()


def query_value(query: str) -> str:
    """``@query`` as RFC 9421 gives it: the query with its ``?``, or ``?`` alone."""
    return "?" + query


def key_id(key: bytes) -> str:
    """The name a key goes by in a signature: the start of its SHA-256."""
    return hashlib.sha256(key).hexdigest()[:16]


def _signed(key: bytes, components: tuple[str, ...], values: tuple[str, ...], digest: str,
            created: int) -> dict[str, str]:
    params = signature_params(components, created, key_id(key))
    base = signature_base(zip(components, values, strict=True), params)
    return {"Content-Digest": digest, "Signature-Input": f"{LABEL}={params}",
            "Signature": f"{LABEL}=:{hmac_sha256(key, base)}:"}


def request_signature(key: bytes, method: str, path: str, query: str, digest: str,
                      created: int) -> dict[str, str]:
    """The headers a board sends with a signed request."""
    return _signed(key, REQUEST_COMPONENTS, (method, path, query_value(query), digest), digest,
                   created)


def answer_signature(key: bytes, status: int, digest: str, method: str, path: str,
                     query: str, created: int, request_digest: str = "") -> dict[str, str]:
    """The headers the server sends with a signed answer to ``method
    path?query``; with ``request_digest``, an answer to that post alone."""
    values = (str(status), digest, method, path, query_value(query))
    if request_digest:
        return _signed(key, POST_ANSWER_COMPONENTS, (*values, request_digest), digest, created)
    return _signed(key, ANSWER_COMPONENTS, values, digest, created)


def derive_key(shared: bytes, device: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"epd board key " + device.encode()).derive(shared)


# ── The keys ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Key:
    key: bytes
    at: float           # when it was approved, asked for, or stopped

    @property
    def id(self) -> str:
        return key_id(self.key)


@dataclass(frozen=True)
class Board:
    """What the server holds for one board: the key it signs with, one that
    waits for a person's approval, and the keys it no longer takes posts
    under."""
    device: str
    approved: Key | None = None
    pending: Key | None = None
    retired: tuple[Key, ...] = ()

    def keys(self) -> list[tuple[str, Key]]:
        named = [("approved", self.approved), ("pending", self.pending)]
        return [(which, k) for which, k in named if k is not None] + [
            ("retired", k) for k in self.retired]


@dataclass(frozen=True)
class Verdict:
    """What the server makes of a board's request. ``state`` is empty when it
    may go on, and else PAIR, PENDING, CLOCK or REFUSED. ``key`` is the key
    the request was shown to be signed with, which signs the refusal."""
    state: str = ""
    device: str = ""
    words: str = ""
    key: bytes | None = None


def _retire(b: Board, *keys: Key | None, at: float) -> tuple[Key, ...]:
    gone = [Key(k.key, at) for k in keys if k is not None]
    return tuple(gone + [k for k in b.retired if all(k.key != g.key for g in gone)])[:RETIRED_KEPT]


class BoardKeys:
    """The keys of the boards named in ``boards``, kept in the JSON file at
    ``path``, and the checks made with them."""

    def __init__(self, path: str, boards: Iterable[str], now: Callable[[], float] = time.time):
        self.path = path
        self.names = tuple(boards)
        self.now = now
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}       # each request signature taken, and when it expires
        self._boards = {name: Board(name) for name in self.names}
        self._boards.update(self._read())

    def _read(self) -> dict[str, Board]:
        try:
            with open(self.path) as f:
                kept = json.load(f)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.error("%s is unreadable (%s): every board must pair again", self.path, exc)
            return {}
        out = {}
        for name, entry in kept.items() if isinstance(kept, dict) else ():
            if name not in self.names or not isinstance(entry, dict):
                continue

            def key(k) -> Key | None:
                if isinstance(k, dict) and isinstance(k.get("key"), str):
                    return Key(bytes.fromhex(k["key"]), float(k.get("at", 0)))
                return None
            retired = entry.get("retired")
            out[name] = Board(name, key(entry.get("approved")), key(entry.get("pending")),
                              tuple(k for k in map(key, retired if isinstance(retired, list)
                                                   else []) if k))
        return out

    def _write(self) -> None:
        def kept(k: Key) -> dict:
            return {"key": k.key.hex(), "at": k.at}
        out = {}
        for b in self._boards.values():
            entry: dict = {which: kept(k) for which, k in (("approved", b.approved),
                                                          ("pending", b.pending)) if k}
            if b.retired:
                entry["retired"] = [kept(k) for k in b.retired]
            if entry:
                out[b.device] = entry
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        part = self.path + ".part"
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(out, f)
        os.replace(part, self.path)

    def boards(self) -> list[Board]:
        return [self._boards[name] for name in self.names]

    def board(self, device: str) -> Board | None:
        return self._boards.get(device)

    def pair(self, device: str, board_half: bytes) -> bytes:
        """The server's half of the exchange, with the key it makes kept as
        ``device``'s pending key, in place of any pending before it.

        Raises:
            ValueError: no board of that name, or a half that is not a point
                on P-256.
        """
        if device not in self._boards:
            raise ValueError(f"no board named {device}")
        theirs = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), board_half)
        ours = ec.generate_private_key(ec.SECP256R1())
        key = derive_key(ours.exchange(ec.ECDH(), theirs), device)
        with self._lock:
            b = self._boards[device]
            now = self.now()
            self._boards[device] = replace(b, pending=Key(key, now),
                                           retired=_retire(b, b.pending, at=now))
            self._write()
        log.warning("%s asks to pair, with key %s: approve it in Settings", device, key_id(key))
        return ours.public_key().public_bytes(serialization.Encoding.X962,
                                              serialization.PublicFormat.UncompressedPoint)

    def approve(self, device: str) -> None:
        """``device``'s pending key in place of its approved one."""
        with self._lock:
            b = self._boards[device]
            if b.pending is None:
                return
            now = self.now()
            self._boards[device] = Board(device, Key(b.pending.key, now), None,
                                         _retire(b, b.approved, at=now))
            self._write()

    def reject(self, device: str) -> None:
        with self._lock:
            b = self._boards[device]
            self._boards[device] = replace(b, pending=None,
                                           retired=_retire(b, b.pending, at=self.now()))
            self._write()

    def forget(self, device: str) -> None:
        """Both keys out of use: the board's next post is told to pair again."""
        with self._lock:
            b = self._boards[device]
            self._boards[device] = Board(device, retired=_retire(b, b.approved, b.pending,
                                                                 at=self.now()))
            self._write()

    def _find(self, keyid: str) -> tuple[Board, str, Key] | None:
        for b in self._boards.values():
            for which, k in b.keys():
                if k.id == keyid:
                    return b, which, k
        return None

    def check_request(self, method: str, path: str, query: str, headers: Mapping[str, str],
                      body: bytes) -> Verdict:
        """What the server makes of a board's request: whether it carries a good
        signature from an approved key, and what the board should do if not."""
        found_input = _INPUT.fullmatch(headers.get("Signature-Input", "").strip())
        found_signature = _SIGNATURE.fullmatch(headers.get("Signature", "").strip())
        if not found_input:
            return Verdict(PAIR, words="Not signed. Pair this board with the server.")
        created, keyid = int(found_input.group(1)), found_input.group(2)
        found = self._find(keyid)
        if found is None:
            return Verdict(PAIR, words="Unknown key. Pair this board with the server again.")
        b, which, k = found
        now = self.now()
        if abs(now - created) > WINDOW_S:
            return Verdict(CLOCK, b.device, f"Signed at {created}, but the server's time is "
                                            f"{int(now)}. Take the server's time.")
        digest = content_digest(body)
        if headers.get("Content-Digest", "").strip() != digest or not found_signature:
            return Verdict(REFUSED, b.device, "The body does not match its signature.")
        expected = request_signature(k.key, method, path, query, digest, created)["Signature"]
        if not hmac.compare_digest(expected, f"{LABEL}=:{found_signature.group(1)}:"):
            return Verdict(REFUSED, b.device, "Bad signature.")
        with self._lock:
            for old in [s for s, until in self._seen.items() if until < now]:
                del self._seen[old]
            if expected in self._seen:
                return Verdict(REFUSED, b.device, "This signature was used before.")
            self._seen[expected] = created + WINDOW_S
        if which == "pending":
            return Verdict(PENDING, b.device, "Key waiting for approval in Settings.", k.key)
        if which == "retired":
            return Verdict(PAIR, b.device, "This key is no longer approved. Pair again.", k.key)
        return Verdict(device=b.device)

    def sign_answer(self, device: str, status: int, digest: str, method: str, path: str,
                    query: str, keyid: str = "") -> dict[str, str]:
        """The headers that sign an answer to ``device``: with the key it names
        by ``keyid``, any the server holds for it, else its approved key; none
        when the server holds no such key."""
        b = self._boards.get(device)
        if b is None:
            return {}
        key = next((k for _, k in b.keys() if k.id == keyid), None) if keyid else b.approved
        if key is None:
            return {}
        return answer_signature(key.key, status, digest, method, path, query, int(self.now()))

    def sign_refusal(self, verdict: Verdict, status: int, digest: str, method: str, path: str,
                     query: str, request_digest: str) -> dict[str, str]:
        """The headers that sign a refusal of a post, with the key the post was
        shown to be signed with; none for a post not shown to be."""
        if verdict.key is None:
            return {}
        return answer_signature(verdict.key, status, digest, method, path, query,
                                int(self.now()), request_digest)
