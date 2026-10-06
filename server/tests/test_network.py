"""The network settings file, against Espressif's own tool and the firmware."""
import csv
import os
import re
import subprocess
import sys

import pytest

from epd_server.config import MqttSettings, NetworkSettings
from epd_server.network import STORE_SIZE, network_settings_file

NETWORK = NetworkSettings(server_url="http://epd.local:8080", wifi_ssid="Home Wi-Fi",
                          wifi_password="correct horse", mqtt_host="broker.local")
MQTT = MqttSettings(enabled=True, host="mosquitto", port=1884, prefix="mqtt/epd")

SETTINGS_CPP = os.path.join(os.path.dirname(__file__), "..", "..", "firmware", "src",
                            "settings.cpp")


def made_by_the_tool(tmp_path, rows) -> bytes:
    """What Espressif's command line makes of ``rows``, at the store's size."""
    source, out = tmp_path / "nvs.csv", tmp_path / "nvs.bin"
    with open(source, "w", newline="") as f:
        csv.writer(f).writerows([("key", "type", "encoding", "value"),
                                 ("epd", "namespace", "", ""), *rows])
    subprocess.run([sys.executable, "-m", "esp_idf_nvs_partition_gen", "generate",
                    str(source), str(out), hex(STORE_SIZE)],
                   check=True, capture_output=True, cwd=tmp_path)
    return out.read_bytes()


def test_the_file_is_what_the_tool_makes_of_the_same_values(tmp_path):
    made = network_settings_file(NETWORK, MQTT, product="my-display", first_page="today.png")

    assert len(made) == STORE_SIZE
    assert made == made_by_the_tool(tmp_path, [
        ("serverURL", "data", "string", "http://epd.local:8080/today.png"),
        ("wifiSSID", "data", "string", "Home Wi-Fi"),
        ("wifiPass", "data", "string", "correct horse"),
        ("mqttEnabled", "data", "u8", "1"),
        ("mqttBroker", "data", "string", "broker.local"),
        ("mqttPort", "data", "i32", "1884"),
        ("mqttClientID", "data", "string", "my-display"),
        ("mqttPrefix", "data", "string", "mqtt/epd"),
    ])


@pytest.mark.parametrize("mqtt", [None, MqttSettings(False, "mosquitto", 1883, "mqtt/epd")])
def test_without_mqtt_the_file_holds_no_mqtt_keys(tmp_path, mqtt):
    made = network_settings_file(NETWORK, mqtt, product="my-display", first_page="/today.png")

    assert made == made_by_the_tool(tmp_path, [
        ("serverURL", "data", "string", "http://epd.local:8080/today.png"),
        ("wifiSSID", "data", "string", "Home Wi-Fi"),
        ("wifiPass", "data", "string", "correct horse"),
    ])


def test_a_missing_key_makes_no_file():
    with pytest.raises(ValueError, match="not set: client.wifi.password, client.mqtt_host"):
        network_settings_file(NetworkSettings("http://epd.local", "Home"), MQTT,
                              product="my-display", first_page="today.png")


def test_the_firmware_reads_the_namespace_and_keys_the_file_holds():
    with open(SETTINGS_CPP) as f:
        source = f.read()

    assert re.search(r'#define SETTINGS_NAMESPACE "epd"', source)
    for key in ("serverURL", "wifiSSID", "wifiPass", "mqttEnabled", "mqttBroker", "mqttPort",
                "mqttClientID", "mqttPrefix"):
        assert f'"{key}"' in source, key
    assert 'putBool("mqttEnabled"' in source and 'putInt("mqttPort"' in source
