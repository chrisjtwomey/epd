"""A small name -> class plugin registry.

One ``Registry`` per plugin kind, so a project can register data sources and
pages independently::

    sources = Registry("data source")

    @sources.register("myservice")
    class MySource:
        def __init__(self, *, apikey, location): ...

    src = sources.create("myservice", apikey="...", location="Dublin",
                         interval=60)   # interval is dropped: not in __init__

``create()`` forwards only the keyword arguments a constructor declares, so
implementations need not accept parameters they do not use. A constructor
that takes ``**kwargs`` receives everything.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, TypeVar

T = TypeVar("T", bound=type)


class Registry:
    def __init__(self, kind: str = "plugin"):
        self.kind = kind
        self._items: dict[str, type] = {}

    # ── registration ────────────────────────────────────────────────────

    def register(self, name: str) -> Callable[[T], T]:
        """Class decorator: ``@registry.register("name")``."""
        def decorator(cls: T) -> T:
            self._items[name] = cls
            return cls
        return decorator

    def add(self, name: str, cls: type) -> None:
        """Register without the decorator."""
        self._items[name] = cls

    # ── lookup ──────────────────────────────────────────────────────────

    def names(self) -> tuple[str, ...]:
        return tuple(self._items.keys())

    def get(self, name: str) -> type:
        try:
            return self._items[name]
        except KeyError:
            supported = ", ".join(sorted(self._items)) or "(none registered)"
            raise ValueError(
                f"Unknown {self.kind} {name!r}. Supported: {supported}"
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)

    # ── construction ────────────────────────────────────────────────────

    def create(self, name: str, **kwargs: Any):
        """Instantiate the class registered under ``name``.

        Keyword arguments the constructor does not declare are dropped,
        unless it accepts ``**kwargs``.
        """
        cls = self.get(name)
        params = inspect.signature(cls.__init__).parameters
        takes_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        if takes_var_kw:
            return cls(**kwargs)
        return cls(**{k: v for k, v in kwargs.items() if k in params})
