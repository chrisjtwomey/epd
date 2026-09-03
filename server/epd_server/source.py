"""Where page content comes from.

A :class:`DataSource` exposes *named datasets*, each behind a zero-argument
fetcher so nothing is fetched until a page actually needs it. Pages declare
the names they need in ``Page.requires``; the pipeline fetches each needed
dataset once per regeneration and hands it to every page that asked for it.

The names are the project's to choose: whatever its pages ask for. This
module never interprets them, and two projects on the same kit need not
agree on any of them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Mapping

Fetcher = Callable[[], Any]


class DataSource(ABC):
    @abstractmethod
    def datasets(self) -> Mapping[str, Fetcher]:
        """Map dataset name -> zero-argument callable that produces it."""

    def invalidate(self) -> None:
        """Drop any caches so the next fetch goes to the origin. No-op by default."""


class StaticSource(DataSource):
    """Fixed values, e.g. a map image URL computed once at startup."""

    def __init__(self, **values: Any):
        self._values = dict(values)

    def datasets(self) -> Mapping[str, Fetcher]:
        return {name: (lambda v=value: v) for name, value in self._values.items()}


class CompositeSource(DataSource):
    """Merge several sources. Dataset names must not collide."""

    def __init__(self, *sources: DataSource):
        self.sources = list(sources)

    def datasets(self) -> Mapping[str, Fetcher]:
        merged: dict[str, Fetcher] = {}
        owner: dict[str, DataSource] = {}
        for src in self.sources:
            for name, fetch in src.datasets().items():
                if name in merged:
                    raise ValueError(
                        f"dataset {name!r} is provided by both "
                        f"{type(owner[name]).__name__} and {type(src).__name__}"
                    )
                merged[name] = fetch
                owner[name] = src
        return merged

    def invalidate(self) -> None:
        for src in self.sources:
            src.invalidate()
