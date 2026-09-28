"""posix_tz: a zone's POSIX TZ string, from its TZif file's footer."""
import zoneinfo
from datetime import timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from epd_server.posix_tz import posix_tz

DUBLIN = b"IST-1GMT0,M10.5.0,M3.5.0/1"


@pytest.fixture
def zones(tmp_path, monkeypatch):
    """A zone database in tmp_path: write(key, bytes) adds a TZif file."""
    monkeypatch.setattr(zoneinfo, "TZPATH", (str(tmp_path),))

    def write(key, data):
        path = tmp_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return write


def tzif(version, footer):
    return b"TZif" + version + b"\0" * 39 + b"\n" + footer + b"\n"


def test_the_footer_comes_back_as_the_database_wrote_it(zones):
    zones("Europe/Dublin", tzif(b"2", DUBLIN))

    assert posix_tz(SimpleNamespace(key="Europe/Dublin")) == DUBLIN.decode()


@pytest.mark.parametrize("data", [
    tzif(b"\0", b""),         # version 1 has no footer
    tzif(b"3", b""),          # no rule after the last change
    b"TZif2" + b"\0" * 39,    # cut short
    b"not a zone file\n",
])
def test_a_file_without_a_footer_gives_none(zones, data):
    zones("Some/Zone", data)

    assert posix_tz(SimpleNamespace(key="Some/Zone")) is None


def test_a_zone_the_database_lacks_gives_none(zones):
    assert posix_tz(SimpleNamespace(key="Nowhere/Zone")) is None


def test_a_fixed_offset_has_no_key_and_gives_none():
    assert posix_tz(timezone(timedelta(hours=1))) is None


def test_a_real_zone_reads_the_file_zoneinfo_reads():
    # Debian writes Dublin's winter as the negative shift, macOS the other way.
    assert posix_tz(ZoneInfo("Europe/Dublin")) in (DUBLIN.decode(), "GMT0IST,M3.5.0/1,M10.5.0")
    assert posix_tz(ZoneInfo("UTC")) == "UTC0"
