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
where this is installed, so add one to your Dockerfile. Pin a tag
instead of `@main` for releases.

## Modules

| Module | Provides |
|---|---|
| `epd_server.config` | `get_prop`, `get_prop_by_keys` — env var > YAML > default, with type coercion. `load_core_config()` validates the `server`, `image`, `mqtt`, `display` and `debug` blocks into typed settings; `load_yaml()` reads the file |
| `epd_server.registry` | `Registry` — name → class, `create()` forwards only declared kwargs |
| `epd_server.cache` | `DiskCache` — JSON file cache with per-key TTL, datetimes round-trip |
| `epd_server.page` | `Page` — build HTML with Airium, then `save()` renders and quantises it. Both steps are pluggable. |
| `epd_server.render` | `Renderer` protocol; `ChromiumRenderer` (headless, via Selenium) is the default |
| `epd_server.quantise` | `Quantiser` protocol; `GreyscaleQuantiser(levels=4)` default, `PaletteQuantiser` for colour panels, `IdentityQuantiser` for none |
| `epd_server.scheduling` | `Pools`, `TimesSchedule`, `IntervalSchedule` — what shows and when; `next_wake`, `next_regen`, `seconds_until` underneath |
| `epd_server.firmware` | `FirmwareStore` — a directory of `<version>.bin`; `ReleaseWatcher` — fill it from a repository's releases; `parse_user_agent`, `is_clean_tag`, `update_applies` — which board an image is an update for |
| `epd_server.mqtt` | `client_log_subscriber` — relay the client's MQTT log topic into Python logging |
| `epd_server.source` | `DataSource` — named, lazily fetched datasets; `StaticSource` for constants; `CompositeSource` to merge |
| `epd_server.pipeline` | `regenerate(pages, source, only=, force_refresh=)` — fetch what the selected pages need, once each; render; save |
| `epd_server.app` | `DisplayServer(pages, source, schedule, tz, …).run()` — routes, `X-Next-*` headers, regen loop, client log relay, signals. `align_process_timezone()` |

## Tests

```sh
pip install -e '.[dev]'
pytest
```

Nothing here needs Chromium or a network: `Page.save()` is tested with a fake `Renderer`,
`DisplayServer` with Flask's test client and a stand-in shutdown event,
and `GreyscaleQuantiser(levels=4)` is checked byte-for-byte against the
algorithm it replaced.

## A whole server

```python
from epd_server import DisplayServer, align_process_timezone, load_core_config, load_yaml
from epd_server.config import MqttSettings

raw  = load_yaml("config.yaml")
core = load_core_config(raw, default_display={"pools": {"now": ["now.png"]},
                                              "schedule": {"type": "times", "08:00:00": "now"}})
align_process_timezone(core.server.timezone)

DisplayServer(
    pages=[NowPage("now", **core.image.page_kwargs(), html_dir=..., png_dir=...)],
    source=Sensors(),
    schedule=core.server.schedule,
    tz=core.server.timezone,
    regen_lead_seconds=core.server.regen_lead_seconds,
    port=core.server.port,
    mqtt=core.mqtt,
).run(once="--once" in sys.argv)
```

`run()` regenerates every page, starts the HTTP server on a thread, relays
the client's MQTT log topic if enabled, and then sleeps until
`regen_lead_seconds` before each scheduled wake, regenerating that wake's
page with a fresh fetch. `SIGTERM` / `SIGINT` stop it cleanly.

Routes come from the page list — `/<page>.png` for each — plus `/`, which
returns the page list, the schedule and the next wake as JSON. The schedule
is checked against the pages at construction, so a typo in `config.yaml`
fails at startup instead of silently regenerating nothing.

## Config

Every epd server shares the same generic blocks. Validate them once, then
read your own keys with the same env-overridable lookups:

```python
from epd_server import ConfigError, load_core_config, load_yaml
from epd_server.config import get_prop_by_keys

raw = load_yaml("config.yaml")
try:
    core = load_core_config(raw, default_display={"pools": {"now": ["now.png"]},
                                              "schedule": {"type": "times", "08:00:00": "now"}})
    broker = get_prop_by_keys(raw, "sensors", "broker", required=True)   # SENSORS_BROKER env works too
except (ConfigError, KeyError) as exc:
    sys.exit(f"config: {exc.args[0]}")

core.server.port, core.server.timezone, core.server.schedule
core.image.page_kwargs()          # -> kwargs for Page(...)
core.mqtt.enabled, core.mqtt.host, core.mqtt.port, core.mqtt.topic
```

```yaml
server:
  port: 8080
  timezone: Europe/Dublin        # IANA; default is the host's zone
  regen_lead_seconds: 120        # regenerate this long before each wake
display:
  pools:                         # what shows: each pool is read in turn
    morning: [now.png]
    evening: [trend.png, week.png]
  schedule:                      # when: one type
    type: times                  # a pool at each HH:MM:SS in server.timezone
    "08:00:00": morning
    "20:00:00": evening
  # schedule:
  #   type: interval             # or a page every N seconds on the wall clock,
  #   every: 300                 # visiting the pools in order (N must divide a day)
  #   order: [morning, evening]  # default: every pool, as listed
  #   reshuffle_hours: 3         # each pool's random start moves this often
image:
  width: 825
  height: 1200
  innerWidth: 825                # content box, <= width
  innerHeight: 1200
  innerAlignX: center            # left | center | right
  innerAlignY: center            # top | center | bottom
client:                          # what the boards this server serves run
  firmware:                      # server-driven client updates
    enabled: false
    dir: firmware                # a directory of <version>.bin, newest wins
    product: my-display          # the client name a board reports
    offer_dev_builds: false      # true also offers to boards not built from a tag
mqtt:                            # relay the client's log topic
  enabled: false
  host: localhost
  port: 1883
  topic: mqtt/epd-client
debug: false
```

`client.firmware` lets the server flash the boards it serves. It sits under
`client` because every key in it describes the board rather than this
server. Put an image in `dir` named for its version, `v1.6.0.bin`, and every
board of that product running a different version is offered it on its next
page fetch. The version is the filename, so nothing else has to be written.
A relative `dir` is resolved against the directory holding `config.yaml`.

A board built from a tag takes the update; one built from a working tree
(`v1.5.1-3-gab12cd4`, `-dirty`, `dev`) is left alone unless
`offer_dev_builds` says otherwise. A project passes its own client name as
`default_firmware_product=` to `load_core_config`, so the config file only
needs `enabled: true`.

Add a `source` block and the server fills `dir` itself, from a
repository's releases:

```yaml
client:
  firmware:
    enabled: true
    source:
      github: owner/repo
      asset: firmware.bin
      poll_seconds: 3600
      token: ""                  # a private repository
```

It asks GitHub for the latest release on a background thread, and takes the
named asset whenever the tag is not the version already held. An `ETag`
makes an unchanged answer cheap. A private repository needs a token, which
belongs in `CLIENT_FIRMWARE_SOURCE_TOKEN` rather than the file. With
`source` set, `product` defaults to the repository name.

Every key can be overridden by an env var named from its path:
`SERVER_PORT`, `IMAGE_INNERWIDTH`, `MQTT_ENABLED`, `DEBUG`.

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

The default stays at four greys, which suits a monochrome Inkplate panel.
