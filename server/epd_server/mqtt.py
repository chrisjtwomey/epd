"""Subscribe to the boards' remote log topics.

Each board publishes its log lines to ``<prefix>/<board>``. This subscriber
takes every board's topic with one subscription, re-emits each line through
Python logging with the board's name, so it lands in the server log
alongside everything else, and hands it to ``on_line`` to keep.
"""
from __future__ import annotations

import logging

import paho.mqtt.client as mqtt
from typing import Callable

from paho.mqtt.enums import CallbackAPIVersion

log = logging.getLogger(__name__)


def client_log_subscriber(host: str, port: int, prefix: str,
                          client_id: str = "epd-server",
                          logger_name: str = "client",
                          on_line: Callable[[str, str], object] | None = None):
    """Start the network loop, which connects in the background and
    subscribes to every board's topic under ``prefix``. ``on_line(board,
    text)`` is called with each line.

    The loop keeps trying while the broker cannot be reached, so a server
    that starts before its broker relays once the broker is up. It subscribes
    again on every reconnect: the broker forgets a clean session's
    subscription when the connection drops.

    Returns the started ``mqtt.Client``, or ``None`` if the loop could not
    start (logged, not raised, because remote logging is optional). Call
    ``loop_stop()`` and ``disconnect()`` on shutdown.
    """
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id)
    client_log = logging.getLogger(logger_name)

    def on_connect(connected, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            log.error("Connection to client logging broker failed")
            return
        log.info("Connected to client logging broker")
        connected.subscribe(f"{prefix}/+")

    def on_connect_fail(_client, _userdata):
        log.warning("Client logging broker at %s:%d not reachable; trying again", host, port)

    def on_disconnect(_client, _userdata, _disconnect_flags, reason_code, _properties):
        if reason_code.is_failure:
            log.error("Unexpected broker disconnection")
            return
        log.info("Disconnected from client logging broker")

    def on_message(_client, _userdata, message):
        if message.retain:
            return  # ignore stale messages
        # A log line is bytes off a wire, and a board can send a malformed
        # one — a truncated buffer flushed from a queue, say. Decode what is
        # there rather than raise, and let nothing out of this callback:
        # paho kills its network thread on an exception here, so one bad
        # message would end remote logging until the server restarts.
        try:
            board = message.topic.rsplit("/", 1)[-1]
            text = message.payload.decode("utf-8", errors="replace").rstrip("\x00").rstrip()
            client_log.info("%s: %s", board, text)
            if on_line is not None:
                on_line(board, text)
        except Exception:  # noqa: BLE001 - remote logging is best-effort
            log.exception("Dropped an unreadable client log message")

    client.on_connect = on_connect
    client.on_connect_fail = on_connect_fail
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    try:
        client.connect_async(host, port, 60)
        client.loop_start()
        return client
    except Exception as e:  # noqa: BLE001 - remote logging is best-effort
        log.error(f"Connection to client logging broker failed: {e}")
        return None
