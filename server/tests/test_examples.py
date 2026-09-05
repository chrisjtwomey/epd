"""The README's quickstart is examples/minimal, file for file.

A reader may copy either, so nothing may differ between them but the path
to this repository. Nothing else keeps them in step. examples/ota is the same
project with updates on; its server has to construct too.
"""
import runpy
from pathlib import Path

import pytest

from epd_server import DisplayServer

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
README = (ROOT / "README.md").read_text()

FILES = ["server.py", "platformio.ini", "src/defaults.cpp", "src/main.cpp"]


@pytest.mark.parametrize("name", FILES)
def test_the_readme_shows_the_minimal_example_file(name):
    text = (EXAMPLES / "minimal" / name).read_text()
    # The example is inside this repository; the quickstart's project is beside it.
    text = text.replace("symlink://../../firmware", "symlink://../epd/firmware")
    assert text.strip() in README, f"{name} differs from the README's quickstart"


def run_example_server(example, monkeypatch, tmp_path) -> DisplayServer:
    """Run an example's server.py up to, but not including, run()."""
    monkeypatch.chdir(tmp_path)
    started = []
    monkeypatch.setattr(DisplayServer, "run", lambda self, *a, **kw: started.append(self))
    runpy.run_path(str(EXAMPLES / example / "server.py"), run_name="__main__")
    (server,) = started
    return server


@pytest.mark.parametrize("example", ["minimal", "ota"])
def test_the_example_server_constructs(example, monkeypatch, tmp_path):
    server = run_example_server(example, monkeypatch, tmp_path)

    (page,) = server.pages
    assert page.name == "clock"
    page.template()   # the HTML, with no browser involved
    assert b'class="time"' in bytes(page.airium)


def test_the_ota_example_offers_images_to_the_panel_it_names(monkeypatch, tmp_path):
    server = run_example_server("ota", monkeypatch, tmp_path)

    assert server.firmware is not None and server.firmware.enabled
    assert server.firmware.product == "my-display"   # CLIENT_NAME in its platformio.ini
    assert server.firmware_store is not None and server.firmware_store.current() is None
