#!/usr/bin/env python3
"""Fails unless PNGdec and EpdBoardInkplate compiled with one line buffer size.

The size changes a PNGdec struct, and a mismatch only shows as a wrong page on a
panel. Reads the output of ``pio run -v`` after a clean build.
"""
import re
import sys

OBJECTS = {"PNGdec": re.compile(r"-o \S+/PNGdec\.cpp\.o\b"), "EpdBoardInkplate": re.compile(r"-o \S+/InkplateBoard\.cpp\.o\b")}
SIZE = re.compile(r"-DPNG_MAX_BUFFERED_PIXELS=(\d+)")


def sizes(log: str) -> dict[str, str | None]:
    """Each library's size, from its compile line; a key is absent with no such line."""
    found: dict[str, str | None] = {}
    for line in log.splitlines():
        for name, compiled in OBJECTS.items():
            if compiled.search(line):
                m = SIZE.search(line)
                found[name] = m.group(1) if m else None
    return found


def problem(found: dict[str, str | None]) -> str | None:
    """What is wrong with ``found``, or None."""
    missing = [name for name in OBJECTS if name not in found]
    if missing:
        return f"no compile line for {', '.join(missing)}: run a clean build with -v"
    if None in found.values() or len(set(found.values())) != 1:
        return f"PNGdec and EpdBoardInkplate disagree on PNG_MAX_BUFFERED_PIXELS: {found}"
    return None


if __name__ == "__main__":
    log = sys.stdin.read()
    found = sizes(log)
    wrong = problem(found)
    if wrong:
        sys.exit(wrong)
    print(f"PNG_MAX_BUFFERED_PIXELS={found['PNGdec']} in both")
