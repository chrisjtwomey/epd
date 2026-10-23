"""The two kinds of answer the server's routes build by hand: a file to
download, and plain text for a person."""
from __future__ import annotations

import io

from flask import make_response, send_file


def download(data: bytes, name: str, mimetype: str = "application/octet-stream"):
    """``data`` as an attachment named ``name``."""
    return make_response(send_file(io.BytesIO(data), mimetype=mimetype, as_attachment=True,
                                   download_name=name))


def text(status: int, message: str):
    """A plain-text answer, for a person reading it in a terminal or a page."""
    rsp = make_response(message + "\n", status)
    rsp.mimetype = "text/plain"
    return rsp
