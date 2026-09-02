"""Turn an HTML file into a PIL image.

:class:`Renderer` is the protocol :class:`epd_server.page.Page` calls;
:class:`ChromiumRenderer` is the default implementation. Any object with a
matching ``render()`` method works — a Playwright wrapper, ``wkhtmltoimage``,
or a fake that returns a synthetic image in tests.
"""
from __future__ import annotations

import io
import logging
import os
from time import sleep
from typing import Protocol, runtime_checkable

from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

log = logging.getLogger(__name__)


@runtime_checkable
class Renderer(Protocol):
    def render(self, html_path: str, width: int, height: int) -> Image.Image:
        """Load ``html_path`` at ``width`` x ``height`` and return a screenshot."""
        ...


class ChromiumRenderer:
    """Headless Chromium via Selenium.

    A fresh browser is started for every render and quit afterwards, so a
    long-running server never accumulates browser state or leaked processes.

    Args:
        binary: Chromium/Chrome executable. Defaults to ``$CHROME_BIN``, then
            ``/usr/bin/chromium``. Only applied when the path exists, so that
            outside Docker Selenium Manager can locate a browser itself.
        driver_path: chromedriver executable. Defaults to
            ``/usr/bin/chromedriver`` when that exists (the Docker image's
            apt-installed driver), else Selenium Manager bootstraps one.
        load_timeout: seconds to wait for ``document.readyState == "complete"``.
        settle_seconds: extra wait after load for any JS drawing (e.g. rough.js).
    """

    DEFAULT_BINARY = "/usr/bin/chromium"
    DEFAULT_DRIVER = "/usr/bin/chromedriver"

    def __init__(
        self,
        binary: str | None = None,
        driver_path: str | None = None,
        load_timeout: float = 10.0,
        settle_seconds: float = 1.0,
    ):
        self.binary = binary or os.environ.get("CHROME_BIN", self.DEFAULT_BINARY)
        if driver_path is None and os.path.exists(self.DEFAULT_DRIVER):
            driver_path = self.DEFAULT_DRIVER
        self.driver_path = driver_path
        self.load_timeout = load_timeout
        self.settle_seconds = settle_seconds

    # ── Pure helpers (unit-testable without a browser) ────────────────────

    def options(self, width: int, height: int) -> Options:
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--hide-scrollbars")
        opts.add_argument(f"--window-size={width},{height}")
        opts.add_argument("--force-device-scale-factor=1")
        # Required in containers: Chromium can't set up its sandbox without
        # extra kernel capabilities, and /dev/shm defaults to 64MB which it
        # exhausts immediately (manifests as "DevToolsActivePort doesn't exist").
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        if os.path.exists(self.binary):
            opts.binary_location = self.binary
        else:
            log.debug("browser binary %s not found; leaving discovery to Selenium Manager",
                      self.binary)
        return opts

    # ── Browser lifecycle ────────────────────────────────────────────────

    def _driver(self, width: int, height: int):
        opts = self.options(width, height)
        if self.driver_path:
            driver = webdriver.Chrome(service=Service(self.driver_path), options=opts)
        else:
            driver = webdriver.Chrome(options=opts)

        driver.set_window_rect(width=width, height=height)
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {"mobile": False, "width": width, "height": height, "deviceScaleFactor": 1},
        )
        return driver

    def render(self, html_path: str, width: int, height: int) -> Image.Image:
        driver = self._driver(width, height)
        try:
            driver.get("file://" + os.path.abspath(html_path))
            WebDriverWait(driver, self.load_timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            sleep(self.settle_seconds)
            png = driver.get_screenshot_as_png()
        finally:
            driver.quit()

        img = Image.open(io.BytesIO(png))
        img.load()  # decode now so the BytesIO can be dropped
        return img
