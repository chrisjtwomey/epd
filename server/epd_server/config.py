"""Resolve config values with environment-variable override.

Precedence for every lookup: **env var > YAML value > default**.

The env-var name is derived from the key path, upper-cased and joined with
underscores: ``("server", "timezone")`` -> ``SERVER_TIMEZONE``. Env strings are
coerced to the type of the YAML value they replace (or of the default when
the YAML key is absent), so ``MQTT_ENABLED=true`` yields ``True`` and
``SERVER_PORT=9090`` yields ``9090``.
"""
from __future__ import annotations

import operator
import os
from functools import reduce
from typing import Any, Callable


def get_by_path(root, items):
    """Access a nested object in ``root`` by a sequence of keys."""
    return reduce(operator.getitem, items, root)


def _env_name(keys) -> str:
    """``("server", "timezone")`` -> ``"SERVER_TIMEZONE"``."""
    return "_".join(str(k).upper() for k in keys)


def _coerce_env(raw: str, reference):
    """Coerce a string env-var value to match the type of ``reference``.

    ``bool`` is checked before ``int`` because ``bool`` subclasses ``int``.
    """
    if isinstance(reference, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(reference, int):
        return int(raw)
    if isinstance(reference, float):
        return float(raw)
    if isinstance(reference, list):
        return [s.strip() for s in raw.split(",") if s.strip()]
    return raw


def _resolve(keys, yaml_lookup: Callable[[], Any], default, required: bool) -> Any:
    """Resolve one value: env var, then ``yaml_lookup()``, then ``default``.

    Raises ``KeyError`` when the value is required and none of the three
    sources provide it.
    """
    raw_env = os.environ.get(_env_name(keys))
    try:
        yaml_val = yaml_lookup()
        yaml_present = True
    except (KeyError, TypeError):
        yaml_val = None
        yaml_present = False

    if raw_env is not None:
        reference = yaml_val if yaml_present else default
        return _coerce_env(raw_env, reference) if reference is not None else raw_env

    if yaml_present:
        return yaml_val

    if default is None and required:
        raise KeyError("{} not in config but is required".format(".".join(keys)))
    return default


def get_prop_by_keys(config, *keys, default=None, required=True) -> Any:
    """Resolve a nested config value, e.g. ``get_prop_by_keys(cfg, "server", "port")``."""
    return _resolve(keys, lambda: get_by_path(config, keys), default, required)


def get_prop(config, prop, default=None, required=True) -> Any:
    """Resolve a top-level config value, e.g. ``get_prop(cfg, "location")``."""
    return _resolve((prop,), lambda: config[prop], default, required)


# ═══════════════════════════════════════════════════════════════════════════
# Typed settings for the blocks every epd server has
# ═══════════════════════════════════════════════════════════════════════════
#
# A project validates its own keys (an API key, a broker topic, a location)
# and calls load_core_config() for the rest. Every check raises ConfigError
# with a message meant for the person editing config.yaml; the caller
# decides whether that means "log and exit".

from dataclasses import dataclass
from datetime import datetime as _datetime
from datetime import tzinfo as _tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .scheduling import Schedule, validate_time_list


class ConfigError(ValueError):
    """A config value is missing or invalid. The message is user-facing."""


def load_yaml(path) -> dict:
    """Read a YAML file into a dict. An empty file is an empty dict."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


@dataclass(frozen=True)
class ServerSettings:
    port: int
    timezone: _tzinfo
    display_schedule: Schedule      # sorted (HH:MM:SS, url_path) pairs
    regen_lead_seconds: int         # regenerate this long before each wake
    debug: bool


@dataclass(frozen=True)
class ImageSettings:
    width: int
    height: int
    inner_width: int
    inner_height: int
    inner_align_x: str              # left | center | right
    inner_align_y: str              # top | center | bottom

    def page_kwargs(self) -> dict:
        """Keyword arguments for :class:`epd_server.page.Page`."""
        return dict(
            width=self.width,
            height=self.height,
            inner_width=self.inner_width,
            inner_height=self.inner_height,
            inner_align_x=self.inner_align_x,
            inner_align_y=self.inner_align_y,
        )


@dataclass(frozen=True)
class MqttSettings:
    enabled: bool
    host: str
    port: int
    topic: str


@dataclass(frozen=True)
class CoreConfig:
    server: ServerSettings
    image: ImageSettings
    mqtt: MqttSettings


def _positive_int(key: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer (got {value!r})")
    return value


def parse_server(
    config: dict,
    *,
    default_schedule: dict | None = None,
    default_port: int = 8080,
    default_regen_lead_seconds: int = 120,
) -> ServerSettings:
    port = _positive_int("server.port", get_prop_by_keys(config, "server", "port", default=default_port))
    if port > 65535:
        raise ConfigError(f"server.port must be <= 65535 (got {port})")

    regen_lead = get_prop_by_keys(config, "server", "regen_lead_seconds",
                                  default=default_regen_lead_seconds)
    if isinstance(regen_lead, bool) or not isinstance(regen_lead, int) or regen_lead < 0:
        raise ConfigError("server.regen_lead_seconds must be a non-negative integer (seconds)")

    raw_schedule = get_prop_by_keys(config, "display_schedule",
                                    default=default_schedule, required=False)
    if raw_schedule is None:
        raise ConfigError("display_schedule is required: a mapping of HH:MM:SS times to image filenames")
    if not isinstance(raw_schedule, dict) or not raw_schedule:
        raise ConfigError("display_schedule must be a non-empty mapping of HH:MM:SS times to image filenames")
    try:
        validate_time_list("display_schedule", list(raw_schedule.keys()))
    except ValueError as exc:
        raise ConfigError(str(exc)) from None
    schedule: Schedule = sorted(
        ((str(t).strip(), str(p).strip()) for t, p in raw_schedule.items()),
        key=lambda x: x[0],
    )

    tz: _tzinfo = _datetime.now().astimezone().tzinfo  # type: ignore[assignment]
    tz_name = get_prop_by_keys(config, "server", "timezone", default=None, required=False)
    if tz_name:
        try:
            tz = ZoneInfo(str(tz_name))
        except ZoneInfoNotFoundError:
            raise ConfigError(
                f"server.timezone '{tz_name}' is not a valid IANA zone (e.g. Europe/Dublin)"
            ) from None

    debug = bool(get_prop(config, "debug", default=False, required=False))

    return ServerSettings(
        port=port,
        timezone=tz,
        display_schedule=schedule,
        regen_lead_seconds=regen_lead,
        debug=debug,
    )


_ALIGN_X = ("left", "center", "right")
_ALIGN_Y = ("top", "center", "bottom")


def parse_image(config: dict, *, default_width: int = 825, default_height: int = 1200) -> ImageSettings:
    width = _positive_int("image.width", get_prop_by_keys(config, "image", "width", default=default_width))
    height = _positive_int("image.height", get_prop_by_keys(config, "image", "height", default=default_height))
    inner_w = _positive_int("image.innerWidth",
                            get_prop_by_keys(config, "image", "innerWidth", default=width))
    inner_h = _positive_int("image.innerHeight",
                            get_prop_by_keys(config, "image", "innerHeight", default=height))
    if inner_w > width:
        raise ConfigError(f"image.innerWidth ({inner_w}) cannot be greater than image.width ({width})")
    if inner_h > height:
        raise ConfigError(f"image.innerHeight ({inner_h}) cannot be greater than image.height ({height})")

    align_x = str(get_prop_by_keys(config, "image", "innerAlignX", default="center")).strip().lower()
    align_y = str(get_prop_by_keys(config, "image", "innerAlignY", default="center")).strip().lower()
    if align_x not in _ALIGN_X:
        raise ConfigError(f"image.innerAlignX must be one of {sorted(_ALIGN_X)} (got {align_x!r})")
    if align_y not in _ALIGN_Y:
        raise ConfigError(f"image.innerAlignY must be one of {sorted(_ALIGN_Y)} (got {align_y!r})")

    return ImageSettings(width, height, inner_w, inner_h, align_x, align_y)


def parse_mqtt(config: dict, *, default_topic: str = "mqtt/epd-client") -> MqttSettings:
    enabled = bool(get_prop_by_keys(config, "mqtt", "enabled", default=False))
    host = str(get_prop_by_keys(config, "mqtt", "host", default="localhost"))
    port = _positive_int("mqtt.port", get_prop_by_keys(config, "mqtt", "port", default=1883))
    topic = str(get_prop_by_keys(config, "mqtt", "topic", default=default_topic))
    return MqttSettings(enabled, host, port, topic)


def load_core_config(
    config: dict,
    *,
    default_schedule: dict | None = None,
    default_port: int = 8080,
    default_regen_lead_seconds: int = 120,
    default_width: int = 825,
    default_height: int = 1200,
    default_mqtt_topic: str = "mqtt/epd-client",
) -> CoreConfig:
    """Validate the generic blocks of a config dict.

    Raises :class:`ConfigError` (a ``ValueError``) on the first problem, with
    a message for the person editing the file. A project validates its own
    keys separately and decides how to report — typically log and exit.
    """
    return CoreConfig(
        server=parse_server(config, default_schedule=default_schedule, default_port=default_port,
                            default_regen_lead_seconds=default_regen_lead_seconds),
        image=parse_image(config, default_width=default_width, default_height=default_height),
        mqtt=parse_mqtt(config, default_topic=default_mqtt_topic),
    )
