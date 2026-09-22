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
