"""The four version declarations agree with each other and with the package.

They are in different languages and no build step reconciles them, so this is
what stops them drifting. The server sends its own to every client in the
X-Server-Version header, which makes a stale one actively misleading.
"""
import importlib.util
import sys
from pathlib import Path

import epd_server

ROOT = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("epd_version", ROOT / "scripts" / "version.py")
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
