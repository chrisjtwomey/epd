"""The names this contract uses on the wire.

Each header is the product's prefix followed by what it says, so anyone
reading the traffic sees the product rather than the library serving it. A
project passes its own prefix to :class:`~epd_server.app.DisplayServer`; the
default suits one that has not chosen a name.

Header names are case-insensitive, so the spelling here is for the reader.
"""
from __future__ import annotations


class Wire:
    """Every header name, for one prefix."""

    def __init__(self, prefix: str = "EPD"):
        cleaned = prefix.strip().strip("-")
        if not cleaned:
            raise ValueError("the header prefix cannot be empty")
        self.prefix = cleaned
        self.device = f"{cleaned}-Device"
        self.device_version = f"{cleaned}-Device-Version"
        self.server_version = f"{cleaned}-Server-Version"
        self.server_epoch = f"{cleaned}-Server-Epoch-Seconds"
        self.next_refresh = f"{cleaned}-Next-Display-Refresh-Seconds"
        self.next_sensor_poll = f"{cleaned}-Next-Sensor-Poll-Seconds"
        self.next_url = f"{cleaned}-Next-URL"
        self.firmware_version = f"{cleaned}-Server-Firmware-Version"
        self.firmware_url = f"{cleaned}-Server-Firmware-URL"


# The names this library used before a project could choose its own. The
# server sends them beside the current ones and reads them from a request, so
# a board flashed before the change keeps working without being reflashed.
#
# Remove these, and the code that uses them, once no such board is left. A
# request that carries only the legacy identity says so in the log.
LEGACY_DEVICE = "X-Client-Name"
LEGACY_DEVICE_VERSION = "X-Client-Version"
LEGACY_SERVER_VERSION = "X-Server-Version"
LEGACY_NEXT_REFRESH = "X-Next-Refresh-Seconds"
LEGACY_NEXT_URL = "X-Next-URL"
LEGACY_FIRMWARE_VERSION = "X-Server-Firmware-Version"
LEGACY_FIRMWARE_URL = "X-Server-Firmware-URL"
