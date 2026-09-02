"""JSON disk cache in epd_server.cache."""
from datetime import datetime

from freezegun import freeze_time

from epd_server.cache import DEFAULT_TTL, DiskCache


def test_miss_returns_none(tmp_path):
    assert DiskCache(tmp_path / "c.json").get("k") is None


def test_set_then_get_roundtrips(tmp_path):
    c = DiskCache(tmp_path / "c.json")
    c.set("k", {"a": 1, "when": datetime(2026, 7, 1, 12, 0)})
    got = c.get("k")
    assert got["a"] == 1
    assert got["when"] == datetime(2026, 7, 1, 12, 0)   # datetime survives JSON


def test_entry_expires_after_ttl(tmp_path):
    c = DiskCache(tmp_path / "c.json")
    with freeze_time("2026-07-01 12:00:00"):
        c.set("k", 1)
    with freeze_time("2026-07-01 12:30:00"):
        assert c.get("k") == 1
    with freeze_time("2026-07-01 13:00:00"):
        assert c.get("k") is None            # 3600s > DEFAULT_TTL (3300s)


def test_ttl_none_never_expires(tmp_path):
    c = DiskCache(tmp_path / "c.json")
    with freeze_time("2026-07-01 12:00:00"):
        c.set("coords", [1, 2])
    with freeze_time("2030-01-01 00:00:00"):
        assert c.get("coords", ttl=None) == [1, 2]


def test_delete_removes_only_named_keys(tmp_path):
    c = DiskCache(tmp_path / "c.json")
    c.set("a", 1); c.set("b", 2); c.set("coords", 3)
    c.delete("a", "b", "missing")
    assert c.get("a") is None and c.get("b") is None
    assert c.get("coords") == 3


def test_corrupt_file_is_treated_as_empty(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json")
    assert DiskCache(p).get("k") is None
