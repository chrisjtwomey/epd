#!/usr/bin/env python3
"""Read or set epd's version, in every file that declares it.

Four files carry it and nothing but this script and its test keeps them in
step. The server reports its own to every client in the X-Server-Version
header, so a disagreement is not cosmetic.

    python3 scripts/version.py            # print the version, or the disagreement
    python3 scripts/version.py 0.3.0      # set all four
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each file, and the pattern whose one capture group is the version.
DECLARATIONS = {
    "firmware/library.json": r'("version"\s*:\s*")([^"]+)(")',
    "firmware/boards/inkplate/library.json": r'("version"\s*:\s*")([^"]+)(")',
    "server/pyproject.toml": r'(^version\s*=\s*")([^"]+)(")',
    "server/epd_server/_version.py": r'(^__version__\s*=\s*")([^"]+)(")',
}

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _pattern(path: str) -> re.Pattern:
    return re.compile(DECLARATIONS[path], re.MULTILINE)


def declared() -> dict[str, str]:
    """Every declared version, by the file that declares it."""
    found = {}
    for path in DECLARATIONS:
        text = (ROOT / path).read_text()
        match = _pattern(path).search(text)
        if match is None:
            raise SystemExit(f"{path}: no version declaration found")
        found[path] = match.group(2)
    return found


def write(version: str) -> None:
    if not SEMVER.match(version):
        raise SystemExit(f"{version!r} is not MAJOR.MINOR.PATCH")
    for path in DECLARATIONS:
        file = ROOT / path
        text = file.read_text()
        file.write_text(_pattern(path).sub(rf"\g<1>{version}\g<3>", text, count=1))
        print(f"{path} -> {version}")


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
    for path, version in found.items():
        print(f"  {version}  {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
