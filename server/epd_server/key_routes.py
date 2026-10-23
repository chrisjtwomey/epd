"""The board keys on the wire: ``POST /pair``, the check of a signed post,
and the signature on the server's answers.

:class:`~epd_server.app.DisplayServer` makes one :class:`KeyRoutes` from its
``board_keys``; the keys themselves are kept in :mod:`epd_server.board_keys`.
"""
from __future__ import annotations

import base64
import logging
from typing import Iterable

from flask import Flask, abort, jsonify, request

from .board_keys import REFUSED, BoardKeys, Verdict, content_digest
from .headers import Wire

log = logging.getLogger(__name__)


class KeyRoutes:
    """With ``require_signatures``, pairing is open and every ingest post
    needs a good signature from an approved key; the image and each query in
    ``signed_queries`` are signed whenever the server holds the board's key."""

    def __init__(self, board_keys: BoardKeys, *, require_signatures: bool,
                 signed_queries: Iterable[str], wire: Wire):
        self.board_keys = board_keys
        self.require_signatures = require_signatures
        self.signed_queries = tuple(signed_queries)
        self.wire = wire

    def register(self, app: Flask) -> None:
        if self.require_signatures:
            app.add_url_rule("/pair", endpoint="pair", view_func=self._pair, methods=["POST"])

    def refusal(self):
        """A 401 for a post without a good signature from an approved key, while
        ``require_signatures`` is on. Its ``<prefix>-Key`` header says what the
        board should do: pair, wait for the approval, take the server's clock,
        or try again later."""
        if not self.require_signatures:
            return None
        verdict = self.board_keys.check_request(
            request.method, request.path, request.query_string.decode("ascii", "replace"),
            request.headers, request.get_data(cache=True))
        stated = (request.headers.get(self.wire.device) or "").strip()
        if not verdict.state and stated and stated != verdict.device:
            verdict = Verdict(REFUSED, verdict.device,
                              f"Signed by the key of {verdict.device}, not {stated}.")
        if not verdict.state:
            return None
        log.warning("refused %s from %s: %s", request.path,
                    verdict.device or stated or "an unnamed client", verdict.words)
        rsp = jsonify(problem=verdict.words)
        rsp.status_code = 401
        rsp.headers[self.wire.key] = verdict.state
        # Signed with the post's own key, so that the board can trust a
        # "pair" that would replace the key it holds.
        rsp.headers.update(self.board_keys.sign_refusal(
            verdict, 401, content_digest(rsp.get_data()), request.method, request.path,
            request.query_string.decode("ascii", "replace"),
            content_digest(request.get_data(cache=True))))
        return rsp

    def sign(self, rsp) -> None:
        """Sign the image, and each answer in ``signed_queries``, for a board
        whose key the server holds: the one it names in ``<prefix>-Key-Id``,
        else its approved one."""
        if rsp.status_code != 200:
            return
        if request.endpoint != "firmware" and request.endpoint not in {
                f"query_{name}" for name in self.signed_queries}:
            return
        device = (request.headers.get(self.wire.device) or "").strip()
        digest = rsp.headers.get("Content-Digest") or content_digest(rsp.get_data())
        rsp.headers.update(self.board_keys.sign_answer(
            device, rsp.status_code, digest, request.method, request.path,
            request.query_string.decode("ascii", "replace"),
            (request.headers.get(self.wire.key_id) or "").strip()))

    def _pair(self):
        """The server's half of a board's key exchange: ``{"device": name,
        "key": base64 point}`` in, ``{"key": base64 point}`` out."""
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, "expected {device, key}")
        try:
            ours = self.board_keys.pair(str(body.get("device", "")),
                                        base64.b64decode(str(body.get("key", "")), validate=True))
        except ValueError as exc:
            abort(400, str(exc))
        return jsonify(key=base64.b64encode(ours).decode())
