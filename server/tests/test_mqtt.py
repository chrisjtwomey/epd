"""The client log relay, with no broker.

paho is replaced by a fake whose connect/subscribe/loop_start do nothing, so
the callbacks the subscriber installs can be called directly.
"""
import logging
from dataclasses import dataclass

import pytest

from epd_server import mqtt as relay


@dataclass
class FakeMessage:
    payload: bytes
    retain: bool = False
    topic: str = "mqtt/epd/my-display"


class FakeClient:
    def __init__(self, *_args, **_kwargs):
        self.on_connect = self.on_disconnect = self.on_message = None
        self.subscribed = None

    def connect(self, *_args, **_kwargs):
        pass

    def subscribe(self, topic):
        self.subscribed = topic

    def loop_start(self):
        pass


@pytest.fixture
def kept():
    """The lines the subscriber handed on, as (board, text)."""
    return []


@pytest.fixture
def on_message(monkeypatch, kept):
    """The subscriber's message callback, wired to a fake broker."""
    monkeypatch.setattr(relay.mqtt, "Client", FakeClient)
    client = relay.client_log_subscriber("localhost", 1883, "mqtt/epd",
                                         on_line=lambda board, text: kept.append((board, text)))
    assert isinstance(client, FakeClient)   # it connected, and it is our fake
    assert client.subscribed == "mqtt/epd/+", "every board's topic, with one subscription"
    return client.on_message


def deliver(on_message, payload, retain=False, topic="mqtt/epd/my-display"):
    on_message(None, None, FakeMessage(payload, retain, topic))


def test_each_line_names_the_board_its_topic_does(on_message, kept, caplog):
    with caplog.at_level(logging.INFO, logger="client"):
        deliver(on_message, b"INFO - fetched", topic="mqtt/epd/canary-dock")
        deliver(on_message, b"INFO - drawn", topic="mqtt/epd/canary-head")
    assert kept == [("canary-dock", "INFO - fetched"), ("canary-head", "INFO - drawn")]
    assert [r.getMessage() for r in caplog.records] == \
        ["canary-dock: INFO - fetched", "canary-head: INFO - drawn"]


def test_a_log_line_reaches_the_client_logger(on_message, caplog):
    with caplog.at_level(logging.INFO, logger="client"):
        deliver(on_message, b"NOTICE - ##### Inkplate10 boot #4 #####")
    assert "##### Inkplate10 boot #4 #####" in caplog.text


def test_a_retained_message_is_ignored(on_message, caplog):
    with caplog.at_level(logging.INFO, logger="client"):
        deliver(on_message, b"stale", retain=True)
    assert caplog.text == ""


def test_a_retained_message_is_not_kept(on_message, kept):
    deliver(on_message, b"stale", retain=True)
    assert kept == []


def test_a_line_that_is_not_utf8_is_logged_and_does_not_raise(on_message, caplog):
    # What a board sent whose log queue handed out a record with no
    # terminator: a readable line, then whatever followed it in memory.
    payload = b"NOTICE - received header EPD-Next-URL: http://host/hourly.png" + b"\xff\xfe\x80"

    with caplog.at_level(logging.INFO, logger="client"):
        deliver(on_message, payload)

    assert "received header EPD-Next-URL" in caplog.text


def test_trailing_padding_is_trimmed(on_message, caplog):
    with caplog.at_level(logging.INFO, logger="client"):
        deliver(on_message, b"NOTICE - a short line\x00\x00\x00")
    assert caplog.records[0].getMessage() == "my-display: NOTICE - a short line"


def test_nothing_a_client_sends_escapes_the_callback(on_message, caplog, monkeypatch):
    """paho kills its network thread on an exception here, ending the relay."""
    def explode(*_args, **_kwargs):
        raise RuntimeError("logging blew up")

    monkeypatch.setattr(logging.getLogger("client"), "info", explode)
    with caplog.at_level(logging.ERROR, logger=relay.log.name):
        deliver(on_message, b"anything")

    assert "Dropped an unreadable client log message" in caplog.text
