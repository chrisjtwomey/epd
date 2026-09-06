#!/usr/bin/env python3
"""Read or set epd's version, everywhere it is declared.

Five declarations carry it and nothing but this script and its test keeps
them in step. Two of them are load-bearing beyond tidiness: the server
reports its own to every client in the X-Server-Version header, and
EpdBoardInkplate's dependency on EpdClient decides which pair of published
libraries a project can resolve.

    python3 scripts/version.py            # print the version, or the disagreement
    python3 scripts/version.py 0.3.1      # set every declaration
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What declares the version, as name -> (file, pattern). Group 2 is the
# version; groups 1 and 3 are put back around it, which is how the caret on
# the dependency survives being rewritten.
DECLARATIONS = {
    "EpdClient": (
        "firmware/library.json",
        r'("version"\s*:\s*")([^"]+)(")',
    ),
    "EpdBoardInkplate": (
        "firmware/boards/inkplate/library.json",
        r'("version"\s*:\s*")([^"]+)(")',
    ),
    # The two libraries are one kit and are published together, so a project
    # may not pair 0.3.x of one with 0.4.x of the other.
    "EpdBoardInkplate -> EpdClient": (
        "firmware/boards/inkplate/library.json",
        r'("name"\s*:\s*"EpdClient"\s*,\s*"version"\s*:\s*"\^)([^"]+)(")',
    ),
    "epd-server": (
        "server/pyproject.toml",
        r'(^version\s*=\s*")([^"]+)(")',
    ),
    "epd_server.__version__": (
        "server/epd_server/_version.py",
        r'(^__version__\s*=\s*")([^"]+)(")',
    ),
}

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def declared() -> dict[str, str]:
    """Every declared version, by what declares it."""
    found = {}
    for name, (path, pattern) in DECLARATIONS.items():
        text = (ROOT / path).read_text()
        match = re.search(pattern, text, re.MULTILINE)
        if match is None:
            raise SystemExit(f"{name}: no version declaration found in {path}")
        found[name] = match.group(2)
    return found


def write(version: str) -> None:
    if not SEMVER.match(version):
        raise SystemExit(f"{version!r} is not MAJOR.MINOR.PATCH")
    for name, (path, pattern) in DECLARATIONS.items():
        file = ROOT / path
        text = file.read_text()
        replaced, count = re.subn(pattern, rf"\g<1>{version}\g<3>", text,
                                  count=1, flags=re.MULTILINE)
        if count != 1:
            raise SystemExit(f"{name}: no version declaration found in {path}")
        file.write_text(replaced)
        print(f"{name} -> {version}")


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        write(argv[1])
        return 0

    found = declared()
    versions = set(found.values())
    if len(versions) == 1:
        print(versions.pop())
        return 0
    print("The declared versions disagree:", file=sys.stderr)
    for name, version in found.items():
        print(f"  {version}  {name}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
