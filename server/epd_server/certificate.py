"""A self-signed certificate for the server's HTTPS port.

A browser lets a page use a serial port only over HTTPS or on localhost, so
the flash page needs one. The certificate is valid for ten years and kept
between starts. A start makes a new one only when the names it must hold
have changed, or when fewer than 30 days of it are left. A browser warns
about it, since nobody vouches for it; a server behind a reverse proxy with
a certificate of its own turns the port off instead.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import os
from typing import Sequence
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

log = logging.getLogger(__name__)

VALID_FOR = dt.timedelta(days=3650)
RENEW_BEFORE = dt.timedelta(days=30)

CERTIFICATE_FILE = "certificate.pem"
KEY_FILE = "key.pem"


def certificate_names(server_url: str) -> list[str]:
    """The names a certificate holds: the host the boards reach this server
    by, then this computer's own."""
    host = urlsplit(server_url).hostname if server_url else None
    return ([host] if host else []) + [n for n in ("localhost", "127.0.0.1") if n != host]


def ensure_certificate(directory: str, names: Sequence[str],
                       now: dt.datetime | None = None) -> tuple[str, str]:
    """The paths of the certificate and its key in ``directory``, made anew
    unless the ones there hold exactly ``names`` and stay valid for 30 days."""
    now = now or dt.datetime.now(dt.timezone.utc)
    certificate_path = os.path.join(directory, CERTIFICATE_FILE)
    key_path = os.path.join(directory, KEY_FILE)
    if _still_good(certificate_path, key_path, names, now):
        return certificate_path, key_path

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + VALID_FOR)
        .add_extension(x509.SubjectAlternativeName([_general_name(n) for n in names]),
                       critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    os.makedirs(directory, exist_ok=True)
    _write(key_path, key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()), mode=0o600)
    _write(certificate_path, certificate.public_bytes(serialization.Encoding.PEM), mode=0o644)
    log.info("Made a certificate for %s, valid until %s", ", ".join(names),
             certificate.not_valid_after_utc.date().isoformat())
    return certificate_path, key_path


def _still_good(certificate_path: str, key_path: str, names: Sequence[str],
                now: dt.datetime) -> bool:
    """Whether the files there are a certificate for ``names`` with its own
    key, valid for at least :data:`RENEW_BEFORE`. A file that cannot be read
    is not."""
    try:
        with open(certificate_path, "rb") as f:
            certificate = x509.load_pem_x509_certificate(f.read())
        with open(key_path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        held = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (OSError, ValueError, x509.ExtensionNotFound):
        return False
    return (
        sorted(str(n.value) for n in held) == sorted(names)
        and certificate.not_valid_after_utc - now > RENEW_BEFORE
        and key.public_key() == certificate.public_key()
    )


def _general_name(name: str) -> x509.GeneralName:
    try:
        return x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        return x509.DNSName(name)


def _write(path: str, data: bytes, mode: int) -> None:
    """Replace ``path`` with ``data``, created with ``mode``, so a key is
    never readable by others, not even while it is written."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    os.fchmod(fd, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
