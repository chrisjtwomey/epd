"""Each published package carries the repository's LICENSE.

Each package is built from its own folder and cannot reach the file at the
root, so each folder holds a copy, and nothing else keeps the copies equal.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

PACKAGES = ["server", "firmware", "firmware/boards/inkplate"]


@pytest.mark.parametrize("folder", PACKAGES)
def test_the_package_carries_the_licence(folder):
    copy = ROOT / folder / "LICENSE"
    assert copy.is_file(), f"{folder} has no LICENSE"
    assert copy.read_text() == (ROOT / "LICENSE").read_text(), f"{folder}/LICENSE differs from LICENSE"
