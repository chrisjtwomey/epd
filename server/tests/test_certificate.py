"""The self-signed certificate: what it holds, and when a start makes a new one."""
import datetime as dt
import ipaddress
import os
import stat

from cryptography import x509

from epd_server.certificate import (CERTIFICATE_FILE, KEY_FILE, RENEW_BEFORE, VALID_FOR,
                                    certificate_names, ensure_certificate)

NOW = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.timezone.utc)
NAMES = ["epd.local", "localhost", "127.0.0.1"]


def held(path) -> x509.Certificate:
    with open(path, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def test_the_names_are_the_boards_host_then_this_computers():
    assert certificate_names("http://epd.local:8080") == NAMES
    assert certificate_names("http://192.168.1.2:8080") == ["192.168.1.2", "localhost", "127.0.0.1"]
    assert certificate_names("http://localhost:8080") == ["localhost", "127.0.0.1"]
    assert certificate_names("") == ["localhost", "127.0.0.1"]


def test_a_certificate_holds_its_names_for_ten_years(tmp_path):
    certificate_path, key_path = ensure_certificate(str(tmp_path), NAMES, now=NOW)

    certificate = held(certificate_path)
    names = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.DNSName) == ["epd.local", "localhost"]
    assert names.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("127.0.0.1")]
    assert certificate.not_valid_after_utc == NOW + VALID_FOR
    assert certificate.issuer == certificate.subject


def test_only_the_server_can_read_the_key(tmp_path):
    _, key_path = ensure_certificate(str(tmp_path / "certificate"), NAMES, now=NOW)
    assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600
    assert sorted(os.listdir(tmp_path / "certificate")) == [CERTIFICATE_FILE, KEY_FILE]


def test_a_start_keeps_a_certificate_that_still_fits(tmp_path):
    certificate_path, _ = ensure_certificate(str(tmp_path), NAMES, now=NOW)
    first = held(certificate_path).serial_number

    later = NOW + VALID_FOR - RENEW_BEFORE - dt.timedelta(days=1)
    ensure_certificate(str(tmp_path), list(reversed(NAMES)), now=later)

    assert held(certificate_path).serial_number == first


def test_a_start_makes_a_new_one_for_other_names(tmp_path):
    certificate_path, _ = ensure_certificate(str(tmp_path), NAMES, now=NOW)
    first = held(certificate_path).serial_number

    ensure_certificate(str(tmp_path), ["epd.lan", "localhost", "127.0.0.1"], now=NOW)

    assert held(certificate_path).serial_number != first


def test_a_start_makes_a_new_one_within_30_days_of_its_end(tmp_path):
    certificate_path, _ = ensure_certificate(str(tmp_path), NAMES, now=NOW)
    later = NOW + VALID_FOR - RENEW_BEFORE + dt.timedelta(hours=1)

    ensure_certificate(str(tmp_path), NAMES, now=later)

    assert held(certificate_path).not_valid_after_utc == later + VALID_FOR


def test_a_start_makes_a_new_one_when_a_file_is_damaged_or_does_not_match(tmp_path):
    certificate_path, key_path = ensure_certificate(str(tmp_path), NAMES, now=NOW)
    first = held(certificate_path).serial_number
    with open(key_path, "w") as f:
        f.write("not a key")

    ensure_certificate(str(tmp_path), NAMES, now=NOW)
    second = held(certificate_path).serial_number
    assert second != first

    os.replace(ensure_certificate(str(tmp_path / "other"), NAMES, now=NOW)[1], key_path)
    ensure_certificate(str(tmp_path), NAMES, now=NOW)
    assert held(certificate_path).serial_number != second
