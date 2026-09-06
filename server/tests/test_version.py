"""The version declarations agree with each other and with the package.

They are in different languages and no build step reconciles them, so this is
what stops them drifting. Two of them do real work: the server sends its own
to every client in the X-Server-Version header, which makes a stale one
actively misleading, and EpdBoardInkplate's dependency on EpdClient decides
which pair of published libraries a project can resolve.
"""
import importlib.util
import json
import sys
from pathlib import Path

import epd_server

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("epd_version", ROOT / "scripts" / "version.py")
assert _spec is not None and _spec.loader is not None, "scripts/version.py is missing"
_module = importlib.util.module_from_spec(_spec)
sys.modules["epd_version"] = _module
_spec.loader.exec_module(_module)


def test_every_declaration_agrees():
    declared = _module.declared()
    assert len(set(declared.values())) == 1, declared


def test_the_package_reports_what_the_files_declare():
    assert set(_module.declared().values()) == {epd_server.__version__}


def test_the_version_is_a_release_number():
    assert _module.SEMVER.match(epd_server.__version__)


def test_the_board_library_pins_the_client_it_was_published_with():
    """The two are one kit, so a project cannot pair 0.3.x with 0.4.x."""
    manifest = json.loads((ROOT / "firmware/boards/inkplate/library.json").read_text())
    dependency = next(d for d in manifest["dependencies"] if d["name"] == "EpdClient")

    # The owner too: without it the registry resolves the name by search.
    assert dependency["owner"] == "chrisjtwomey"
    assert dependency["version"] == f"^{manifest['version']}"
