"""Resolve config values with environment-variable override.

Precedence for every lookup: **env var > YAML value > default**.

The env-var name is derived from the key path, upper-cased and joined with
underscores: ``("weather", "apikey")`` -> ``WEATHER_APIKEY``. Env strings are
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
    """``("weather", "apikey")`` -> ``"WEATHER_APIKEY"``."""
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
