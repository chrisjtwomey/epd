# epd-server

The generic half of a scheduled e-paper image server: config resolution,
a plugin registry, a disk cache, HTML-to-PNG page rendering, and the
DST-correct wake/regeneration maths behind the `X-Next-Refresh-Seconds` /
`X-Next-URL` headers.

A project supplies its pages and its data sources; this package supplies
everything that does not depend on what is being displayed.

## Install

Local checkout, editable:

```sh
pip install -e ../epd/server
```

From GitHub, in a `requirements.txt`:

```
epd-server @ git+https://github.com/chrisjtwomey/epd.git@main#subdirectory=server
```

pip honours `#subdirectory=` only for VCS URLs, so a git binary is needed
where this is installed (the weather-cal Dockerfile adds one). Pin a tag
instead of `@main` for releases.

## Modules

| Module | Provides |
|---|---|
| `epd_server.config` | `get_prop`, `get_prop_by_keys` — env var > YAML > default, with type coercion |
| `epd_server.registry` | `Registry` — name → class, `create()` forwards only declared kwargs |
| `epd_server.cache` | `DiskCache` — JSON file cache with per-key TTL, datetimes round-trip |
| `epd_server.page` | `Page` — build HTML with Airium, then `save()` renders and quantises it. Both steps are pluggable. |
| `epd_server.render` | `Renderer` protocol; `ChromiumRenderer` (headless, via Selenium) is the default |
| `epd_server.quantise` | `Quantiser` protocol; `GreyscaleQuantiser(levels=4)` default, `PaletteQuantiser` for colour panels, `IdentityQuantiser` for none |
| `epd_server.scheduling` | `next_wake`, `next_regen`, `seconds_until`, `validate_time_list` |
| `epd_server.mqtt` | `client_log_subscriber` — relay the client's MQTT log topic into Python logging |
| `epd_server.source` | `DataSource` — named, lazily fetched datasets; `StaticSource` for constants; `CompositeSource` to merge |
| `epd_server.pipeline` | `regenerate(pages, source, only=, force_refresh=)` — fetch what the selected pages need, once each; render; save |

## Tests

```sh
pip install -e '.[dev]'
pytest
```

Nothing here needs Chromium: `Page.save()` is tested with a fake `Renderer`,
and `GreyscaleQuantiser(levels=4)` is checked byte-for-byte against the
algorithm it replaced.

## Wiring a project

A project supplies pages and a data source; the kit joins them.

```python
from epd_server import Page, DataSource, StaticSource, CompositeSource, SkipPage, regenerate

class Sensors(DataSource):
    def datasets(self):
        return {"readings": self.read_now, "history": self.read_history}   # lazy
    def invalidate(self):
        self.cache.clear()

class NowPage(Page):
    requires = ("readings",)                       # names from datasets()
    def template(self, readings):                  # arrives as kwargs
        ...build self.airium...

class TrendPage(Page):
    requires = ("readings", "history")
    def template(self, readings, history):
        if len(history) < 2:
            raise SkipPage("not enough history yet")   # keeps the old PNG
        ...

pages  = [NowPage("now", 800, 600, html_dir=..., png_dir=...), TrendPage(...)]
source = CompositeSource(StaticSource(title="Kitchen"), Sensors())

regenerate(pages, source)                          # all pages, each dataset fetched once
regenerate(pages, source, only="trend.png", force_refresh=True)
```

`regenerate` raises `ValueError` for an unknown `only`, and `KeyError` if a
page requires a dataset the source does not provide — both before fetching
anything.

## Matching a panel

```python
from epd_server import Page, GreyscaleQuantiser, PaletteQuantiser

Page(..., quantiser=GreyscaleQuantiser(levels=2))   # 1-bit mono
Page(..., quantiser=GreyscaleQuantiser(levels=8))   # 3-bit grey (Inkplate 10, 5 Gen2)
Page(..., quantiser=PaletteQuantiser([               # 7-colour ACeP
    (0,0,0), (255,255,255), (0,255,0), (0,0,255),
    (255,0,0), (255,255,0), (255,128,0),
]))
```

The default stays at four greys, which is what the weather calendar shipped with.
