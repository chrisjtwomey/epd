"""Whether a board and a server can work together, judged by their versions.

They match when their major numbers match, or, while the major is 0, their
major and minor. That is semantic versioning's own rule: before 1.0.0 a minor
release may break the contract, and after it only a major one may.

The firmware applies the same rule in ``version_compat.h``, so both ends
reach the same answer about each other.
"""
from __future__ import annotations

import re

# "v1.2.3", then anything git describe or semver adds: "-44-g2fe55a4-dirty".
_VERSION = re.compile(r"[vV]?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?")
# What git describe adds to a build past a tag: how many commits past it.
_DESCRIBE = re.compile(r"-(\d+)-g[0-9a-fA-F]+(?:-dirty)?")


def compatibility_key(version: str | None) -> tuple[int, ...] | None:
    """The part of a version that decides compatibility, or None when it is
    not a version that can be read, such as ``dev``."""
    if not version:
        return None
    m = _VERSION.fullmatch(version.strip())
    if m is None:
        return None
    major, minor = int(m[1]), int(m[2])
    return (0, minor) if major == 0 else (major,)


def version_order(version: str | None) -> tuple[int, int, int, int] | None:
    """``(major, minor, patch, commits past the tag)`` for sorting versions,
    or None when it is not a version that can be read. A build past a tag
    sorts after the tag, and after a build fewer commits past it."""
    if not version:
        return None
    version = version.strip()
    m = _VERSION.fullmatch(version)
    if m is None:
        return None
    past = _DESCRIBE.fullmatch(version[m.end(3):])
    return int(m[1]), int(m[2]), int(m[3]), int(past[1]) if past else 0


def compatible(a: str | None, b: str | None) -> bool | None:
    """True or False when both can be judged; None when either cannot."""
    ka, kb = compatibility_key(a), compatibility_key(b)
    if ka is None or kb is None:
        return None
    return ka == kb
