"""ChromiumRenderer configuration — everything testable without a browser."""
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


def test_explicit_driver_path_is_kept():
    assert ChromiumRenderer(driver_path="/x/driver").driver_path == "/x/driver"


def test_timeouts_are_configurable():
    r = ChromiumRenderer(load_timeout=3.5, settle_seconds=0)
    assert r.load_timeout == 3.5 and r.settle_seconds == 0


def test_is_a_renderer():
    assert isinstance(ChromiumRenderer(), Renderer)
    assert not isinstance(object(), Renderer)
