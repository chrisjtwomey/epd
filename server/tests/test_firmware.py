"""Firmware: the User-Agent parser, the applies rule, and the image store."""
import os

import pytest

from epd_server.config import FirmwareSettings
from epd_server.firmware import (
    ClientId,
    FirmwareStore,
    is_clean_tag,
    parse_user_agent,
    update_applies,
)

IMAGE = b"\xe9" + b"\x00" * 63


def settings(**kw) -> FirmwareSettings:
    return FirmwareSettings(**{"enabled": True, "dir": "firmware",
                               "product": "weather-cal", "offer_dev_builds": False, **kw})


# ---------- parse_user_agent ----------

@pytest.mark.parametrize("ua, expected", [
    ("inkplate10-weather-cal/v1.5.1 (Inkplate10)", ClientId("inkplate10-weather-cal", "v1.5.1", "Inkplate10")),
    ("EpdClient/dev", ClientId("EpdClient", "dev", "")),
    ("  EpdClient/v1.0.0 (Inkplate5V2)  ", ClientId("EpdClient", "v1.0.0", "Inkplate5V2")),
    ("cal/v1.5.1-3-gab12cd4-dirty (Inkplate10)", ClientId("cal", "v1.5.1-3-gab12cd4-dirty", "Inkplate10")),
])
def test_parses_the_user_agent_the_client_builds(ua, expected):
    assert parse_user_agent(ua) == expected


@pytest.mark.parametrize("ua", [
    None, "", "   ",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",   # two products
    "curl 8.4.0",                                                          # no slash
    "/v1.0.0",                                                             # no name
])
def test_anything_else_does_not_parse(ua):
    assert parse_user_agent(ua) is None


# ---------- is_clean_tag ----------

@pytest.mark.parametrize("version, clean", [
    ("v1.5.1", True), ("1.5.1", True), ("v1.5", True), ("v10.0.12", True),
    ("v1.5.1-3-gab12cd4", False), ("v1.5.1-dirty", False), ("dev", False), ("", False),
])
def test_only_a_version_built_from_a_tag_is_clean(version, clean):
    assert is_clean_tag(version) is clean


# ---------- update_applies ----------

def test_a_newer_image_applies_to_a_release_board(tmp_path):
    store = FirmwareStore(str(tmp_path))
    image = store.put("v1.6.0", IMAGE)
    client = ClientId("weather-cal", "v1.5.1", "Inkplate10")
    assert update_applies(client, image, settings()) is True


@pytest.mark.parametrize("client, image_version, kw", [
    (ClientId("weather-cal", "v1.5.1"), "v1.6.0", {"enabled": False}),      # switched off
    (ClientId("env-monitor", "v1.5.1"), "v1.6.0", {}),                      # another product
    (ClientId("weather-cal", "v1.6.0"), "v1.6.0", {}),                      # already on it
    (ClientId("weather-cal", "dev"), "v1.6.0", {}),                         # a developer build
    (ClientId("weather-cal", "v1.5.1-3-gab12cd4"), "v1.6.0", {}),           # past the tag
])
def test_no_update_applies(tmp_path, client, image_version, kw):
    image = FirmwareStore(str(tmp_path)).put(image_version, IMAGE)
    assert update_applies(client, image, settings(**kw)) is False


def test_a_developer_build_is_offered_only_when_asked_for(tmp_path):
    image = FirmwareStore(str(tmp_path)).put("v1.6.0", IMAGE)
    client = ClientId("weather-cal", "v1.5.1-3-gab12cd4-dirty")
    assert update_applies(client, image, settings(offer_dev_builds=True)) is True


def test_nothing_applies_without_a_client_or_an_image():
    assert update_applies(None, None, settings()) is False
    assert update_applies(ClientId("weather-cal", "v1.5.1"), None, settings()) is False
    assert update_applies(None, None, None) is False


# ---------- FirmwareStore ----------

def test_an_empty_or_missing_directory_holds_nothing(tmp_path):
    assert FirmwareStore(str(tmp_path / "nope")).current() is None
    assert FirmwareStore(str(tmp_path)).current() is None


def test_put_names_the_file_for_the_version_and_reports_size_and_md5(tmp_path):
    import hashlib
    store = FirmwareStore(str(tmp_path))
    image = store.put("v1.6.0", IMAGE)

    assert os.path.basename(image.path) == "v1.6.0.bin"
    assert image.version == "v1.6.0"
    assert image.size == len(IMAGE)
    assert image.md5 == hashlib.md5(IMAGE).hexdigest()
    assert store.current() == image


def test_put_replaces_the_previous_image_and_leaves_no_temporary_file(tmp_path):
    store = FirmwareStore(str(tmp_path))
    store.put("v1.6.0", IMAGE)
    store.put("v1.7.0", IMAGE + b"\x01")

    assert sorted(os.listdir(tmp_path)) == ["v1.7.0.bin"]
    assert store.current().version == "v1.7.0"


def test_an_image_copied_in_by_hand_is_current(tmp_path):
    (tmp_path / "v2.0.0.bin").write_bytes(IMAGE)
    assert FirmwareStore(str(tmp_path)).current().version == "v2.0.0"


def test_the_newest_file_wins_when_several_are_present(tmp_path):
    (tmp_path / "v1.0.0.bin").write_bytes(IMAGE)
    (tmp_path / "v2.0.0.bin").write_bytes(IMAGE)
    os.utime(tmp_path / "v2.0.0.bin", ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    os.utime(tmp_path / "v1.0.0.bin", ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    assert FirmwareStore(str(tmp_path)).current().version == "v2.0.0"


def test_a_file_whose_name_is_not_a_version_is_ignored_with_a_warning(tmp_path, caplog):
    (tmp_path / ".hidden.bin").write_bytes(IMAGE)
    with caplog.at_level("WARNING"):
        assert FirmwareStore(str(tmp_path)).current() is None
    assert "rename it to <version>.bin" in caplog.text


def test_put_refuses_a_version_that_is_not_a_filename(tmp_path):
    store = FirmwareStore(str(tmp_path))
    for bad in ("", "../v1.6.0", "v1 6 0", "v1/6"):
        with pytest.raises(ValueError, match="cannot be a filename"):
            store.put(bad, IMAGE)
    assert os.listdir(tmp_path) == []


def test_put_refuses_anything_that_is_not_an_esp32_image(tmp_path):
    with pytest.raises(ValueError, match="0xE9 magic"):
        FirmwareStore(str(tmp_path)).put("v1.6.0", b"<!doctype html>")


def test_the_md5_is_recomputed_when_the_file_changes(tmp_path):
    import hashlib
    store = FirmwareStore(str(tmp_path))
    store.put("v1.6.0", IMAGE)
    replaced = IMAGE + b"\x02\x03"
    (tmp_path / "v1.6.0.bin").write_bytes(replaced)
    os.utime(tmp_path / "v1.6.0.bin", ns=(3_000_000_000_000_000_000, 3_000_000_000_000_000_000))

    assert store.current().md5 == hashlib.md5(replaced).hexdigest()


# ---------- ReleaseWatcher ----------

import json  # noqa: E402
import threading  # noqa: E402

from epd_server.config import FirmwareSource  # noqa: E402
from epd_server.firmware import ReleaseWatcher  # noqa: E402


def source(**kw) -> FirmwareSource:
    return FirmwareSource(**{"github": "chrisjtwomey/weather-cal", "asset": "firmware.bin",
                             "poll_seconds": 3600, "token": "", **kw})


class FakeGitHub:
    """Answers the two requests a watcher makes, and records what it was asked."""

    def __init__(self, tag="v1.6.0", asset_name="firmware.bin", data=IMAGE,
                 size=None, status=200, etag='W/"abc"'):
        self.release = {
            "tag_name": tag,
            "assets": [{
                "name": asset_name,
                "size": len(data) if size is None else size,
                "browser_download_url": "https://github.com/dl/firmware.bin",
                "url": "https://api.github.com/repos/x/y/releases/assets/1",
            }],
        }
        self.data = data
        self.status = status
        self.etag = etag
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        if url.endswith("/releases/latest"):
            if self.status != 200:
                return self.status, {}, b""
            if headers.get("If-None-Match") == self.etag:
                return 304, {"ETag": self.etag}, b""
            return 200, {"ETag": self.etag}, json.dumps(self.release).encode()
        return 200, {}, self.data


def watcher(tmp_path, github: FakeGitHub, **kw) -> ReleaseWatcher:
    return ReleaseWatcher(FirmwareStore(str(tmp_path)), source(**kw), fetch=github)


def test_a_new_release_is_downloaded_and_stored(tmp_path):
    github = FakeGitHub()
    w = watcher(tmp_path, github)

    image = w.check_once()

    assert image is not None and image.version == "v1.6.0"
    assert w.store.current().version == "v1.6.0"
    assert github.calls[1][0] == "https://github.com/dl/firmware.bin"


def test_the_release_already_held_is_not_downloaded_again(tmp_path):
    github = FakeGitHub()
    w = watcher(tmp_path, github)
    w.check_once()
    github.calls.clear()
    w.etag = None                       # force the release request through

    assert w.check_once() is None
    assert len(github.calls) == 1       # the release, never the asset


def test_the_etag_makes_the_second_check_a_304(tmp_path):
    github = FakeGitHub()
    w = watcher(tmp_path, github)
    w.check_once()

    assert w.check_once() is None
    assert github.calls[-1][1]["If-None-Match"] == 'W/"abc"'


def test_a_private_repository_sends_the_token_and_uses_the_api_asset_url(tmp_path):
    github = FakeGitHub()
    w = watcher(tmp_path, github, token="ghp_secret")

    w.check_once()

    release_headers, asset_headers = github.calls[0][1], github.calls[1][1]
    assert release_headers["Authorization"] == "Bearer ghp_secret"
    assert asset_headers["Accept"] == "application/octet-stream"
    assert github.calls[1][0] == "https://api.github.com/repos/x/y/releases/assets/1"


@pytest.mark.parametrize("github, match", [
    (FakeGitHub(asset_name="other.bin"), "no asset named firmware.bin"),
    (FakeGitHub(size=999), "expected 999"),
    (FakeGitHub(status=403), "GitHub answered 403"),
    (FakeGitHub(tag=""), "no tag_name"),
])
def test_a_bad_answer_raises_and_stores_nothing(tmp_path, github, match):
    w = watcher(tmp_path, github)
    with pytest.raises(RuntimeError, match=match):
        w.check_once()
    assert w.store.current() is None


def test_run_checks_then_waits_the_poll_interval(tmp_path):
    github = FakeGitHub()
    w = watcher(tmp_path, github, poll_seconds=1800)
    waits = []
    w.stop_event = _StopAfter(waits, 2)

    w.run()

    assert waits == [1800, 1800]
    assert w.store.current().version == "v1.6.0"


def test_run_retries_sooner_after_a_failure_then_backs_off(tmp_path):
    w = watcher(tmp_path, FakeGitHub(status=500), poll_seconds=1800)
    waits = []
    w.stop_event = _StopAfter(waits, 4)

    w.run()

    assert waits == [60, 120, 240, 480]


def test_run_returns_when_the_stop_event_is_set(tmp_path):
    w = watcher(tmp_path, FakeGitHub())
    w.stop_event.set()

    w.run()

    assert w.store.current() is None    # never checked


class _StopAfter(threading.Event):
    """Records each wait and reports a shutdown after n of them."""

    def __init__(self, waits, n):
        super().__init__()
        self.waits = waits
        self.n = n

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return len(self.waits) >= self.n
