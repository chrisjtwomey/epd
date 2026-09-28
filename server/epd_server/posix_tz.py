"""A time zone as a POSIX TZ string, the form a board's C library reads."""
from __future__ import annotations

import os
import zoneinfo
from importlib import resources


def posix_tz(tz) -> str | None:
    """The rule ``tz`` follows after its last listed change, as a POSIX TZ string.

    It is the footer of the zone's TZif file, as the zone database wrote it.
    None for a zone with no IANA key (a fixed offset), a TZif file older than
    version 2, or an empty footer.
    """
    key = getattr(tz, "key", None)
    data = _tzif(key) if key else None
    if not data or data[:4] != b"TZif" or data[4:5] < b"2" or not data.endswith(b"\n"):
        return None
    start = data.rfind(b"\n", 0, len(data) - 1)
    if start < 0:
        return None
    return data[start + 1:-1].decode("ascii") or None


def _tzif(key: str) -> bytes | None:
    """The zone's TZif file, from where :mod:`zoneinfo` looks: TZPATH, then tzdata."""
    for root in zoneinfo.TZPATH:
        path = os.path.join(root, key)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read()
    try:
        return resources.files("tzdata").joinpath("zoneinfo", *key.split("/")).read_bytes()
    except (ModuleNotFoundError, OSError):
        return None
