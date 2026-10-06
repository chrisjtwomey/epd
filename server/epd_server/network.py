"""The network settings a USB flash writes to a board, as a file.

The file is the board's whole settings store, the ESP32's NVS partition,
holding the namespace and keys that ``loadConfig()`` in the firmware's
``settings.cpp`` reads. Written at :data:`STORE_OFFSET`, it replaces
everything the board kept there.
"""
from __future__ import annotations

import io

from esp_idf_nvs_partition_gen import nvs_partition_gen as nvs

from .config import MqttSettings, NetworkSettings

# The store's place in every default partition table.
STORE_OFFSET = 0x9000
STORE_SIZE = 0x5000

# The tool keeps the last page of the store empty. Its command line takes
# that page off the size it is given; its API does not.
_RESERVED_PAGE = 0x1000


def network_settings_file(network: NetworkSettings, mqtt: MqttSettings | None, *,
                          product: str, first_page: str) -> bytes:
    """The settings store for a board of ``product``.

    The board's server URL is ``network.server_url`` with ``first_page``: the
    display fetches that page first, and the dock keeps only the host. Without
    MQTT the file holds no MQTT keys, so the board connects to no broker.

    Raises:
        ValueError: ``network.missing(mqtt)`` names a key.
    """
    missing = network.missing(mqtt)
    if missing:
        raise ValueError(f"not set: {', '.join(missing)}")
    out = io.BytesIO()
    store = nvs.nvs_open(out, STORE_SIZE - _RESERVED_PAGE, nvs.Page.VERSION2)
    nvs.write_entry(store, "epd", "namespace", "", "")
    nvs.write_entry(store, "serverURL", "data", "string",
                    f"{network.server_url}/{first_page.lstrip('/')}")
    nvs.write_entry(store, "wifiSSID", "data", "string", network.wifi_ssid)
    nvs.write_entry(store, "wifiPass", "data", "string", network.wifi_password)
    if mqtt is not None and mqtt.enabled:
        nvs.write_entry(store, "mqttEnabled", "data", "u8", "1")
        nvs.write_entry(store, "mqttBroker", "data", "string", network.mqtt_host)
        nvs.write_entry(store, "mqttPort", "data", "i32", str(mqtt.port))
        nvs.write_entry(store, "mqttClientID", "data", "string", product)
        nvs.write_entry(store, "mqttPrefix", "data", "string", mqtt.prefix)
    nvs.nvs_close(store)
    return out.getvalue()
