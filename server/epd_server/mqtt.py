"""Subscribe to the e-paper client's remote log topic.

The client firmware can publish its log lines to an MQTT topic. This
subscriber re-emits them through Python logging so they land in the server
log alongside everything else.
"""
from __future__ import annotations

import logging

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

log = logging.getLogger(__name__)


def client_log_subscriber(host: str, port: int, topic: str,
                          client_id: str = "epd-server",
                          logger_name: str = "client"):
    """Connect, subscribe to ``topic`` and start the network loop.

    Returns the connected ``mqtt.Client``, or ``None`` if the connection
    failed (the failure is logged, not raised, because remote logging is
    optional). Call ``loop_stop()`` and ``disconnect()`` on shutdown.
    """
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id)
    client_log = logging.getLogger(logger_name)

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            log.error("Connection to client logging broker failed")
            return
        log.info("Connected to client logging broker")

    def on_disconnect(_client, _userdata, _disconnect_flags, reason_code, _properties):
        if reason_code.is_failure:
            log.error("Unexpected broker disconnection")
            return
        log.info("Disconnected from client logging broker")

    def on_message(_client, _userdata, message):
        if message.retain:
            return  # ignore stale messages
        client_log.info(message.payload.decode())

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    try:
        client.connect(host, port, 60)
        client.subscribe(topic)
        client.loop_start()
        return client
    except Exception as e:  # noqa: BLE001 - remote logging is best-effort
        log.error(f"Connection to client logging broker failed: {e}")
        return None
