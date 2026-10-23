"""ChromiumRenderer configuration, and its use of the browser, without one."""
import io

import pytest
from PIL import Image

from epd_server import render as render_module
from epd_server.render import ChromiumRenderer, Renderer


def test_options_carry_size_and_container_flags(tmp_path):
    r = ChromiumRenderer(binary=str(tmp_path / "nope"), driver_path=None)
    args = r.options(825, 1200).arguments
    for flag in ("--headless", "--hide-scrollbars", "--window-size=825,1200",
                 "--force-device-scale-factor=1", "--no-sandbox",
                 "--disable-dev-shm-usage", "--disable-gpu"):
        assert flag in args


def test_binary_location_is_set_only_when_the_path_exists(tmp_path):
    missing = ChromiumRenderer(binary=str(tmp_path / "nope"))
    assert not missing.options(10, 10).binary_location

    fake = tmp_path / "chromium"
    fake.write_text("")
    present = ChromiumRenderer(binary=str(fake))
    assert present.options(10, 10).binary_location == str(fake)


def test_binary_defaults_to_chrome_bin_env_then_system_path(monkeypatch):
    monkeypatch.setenv("CHROME_BIN", "/opt/x/chrome")
    assert ChromiumRenderer().binary == "/opt/x/chrome"
    monkeypatch.delenv("CHROME_BIN")
    assert ChromiumRenderer().binary == ChromiumRenderer.DEFAULT_BINARY


def test_is_a_renderer():
    assert isinstance(ChromiumRenderer(), Renderer)
    assert not isinstance(object(), Renderer)



class FakeDriver:
    """What render() asks of Chrome: a page, its state, a screenshot."""

    def __init__(self, fail_on_get=False):
        self.fail_on_get = fail_on_get
        self.opened = None
        self.quit_calls = 0

    def set_window_rect(self, **_):
        pass

    def execute_cdp_cmd(self, *_):
        pass

    def get(self, url):
        if self.fail_on_get:
            raise RuntimeError("page did not load")
        self.opened = url

    def execute_script(self, _):
        return "complete"

    def get_screenshot_as_png(self):
        out = io.BytesIO()
        Image.new("RGB", (4, 3), "white").save(out, "PNG")
        return out.getvalue()

    def quit(self):
        self.quit_calls += 1


@pytest.fixture
def driver(monkeypatch):
    made = FakeDriver()
    monkeypatch.setattr(render_module.webdriver, "Chrome", lambda **_: made)
    return made


def test_a_page_is_rendered_from_its_file_and_the_browser_quits(driver, tmp_path):
    page = tmp_path / "today.html"
    img = ChromiumRenderer(settle_seconds=0).render(str(page), 4, 3)
    assert img.size == (4, 3)
    assert driver.opened == "file://" + str(page)
    assert driver.quit_calls == 1


# A browser left running after each failed page would fill the server.
def test_the_browser_quits_when_the_page_fails(driver, tmp_path):
    driver.fail_on_get = True
    with pytest.raises(RuntimeError):
        ChromiumRenderer(settle_seconds=0).render(str(tmp_path / "x.html"), 4, 3)
    assert driver.quit_calls == 1
