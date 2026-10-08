# epd-server

The generic half of a scheduled e-paper image server: config resolution,
a plugin registry, a disk cache, HTML-to-PNG page rendering, and the
DST-correct wake/regeneration maths behind the `EPD-Next-Display-Refresh-Seconds` /
`EPD-Next-URL` headers.

A project supplies its pages and its data sources; this package supplies
everything that does not depend on what is being displayed.

## Install

From PyPI:

```sh
pip install "epd-server~=0.10.1"
```

In a project's `requirements.txt`, pin the release that the project's
firmware is built with, because the two share the header contract:

```
epd-server==0.10.1
```

To work on the package, install a checkout editable:

```sh
pip install -e ../epd/server
```

Install it after the project's requirements. A later `pip install -r` puts
the pinned release back whenever the checkout declares another version.

## Modules

| Module | Provides |
|---|---|
| `epd_server.config` | `get_prop`, `get_prop_by_keys` — env var > YAML > default, with type coercion. `load_core_config()` validates the `server`, `image`, `mqtt`, `display` and `debug` blocks into typed settings; `load_yaml()` reads the file |
| `epd_server.registry` | `Registry` — name → class, `create()` forwards only declared kwargs |
| `epd_server.cache` | `DiskCache` — JSON file cache with per-key TTL, datetimes round-trip |
| `epd_server.page` | `Page` — build HTML with Airium, then `save()` renders and quantises it. Both steps are pluggable. |
| `epd_server.render` | `Renderer` protocol; `ChromiumRenderer` (headless, via Selenium) is the default |
| `epd_server.quantise` | `Quantiser` protocol; `GreyscaleQuantiser(levels=4)` default, `PaletteQuantiser` for colour panels, `IdentityQuantiser` for none |
| `epd_server.scheduling` | `Pools`, `TimesSchedule`, `TimeRangesSchedule` — what shows and when; `next_wake`, `next_regen`, `seconds_until` underneath |
| `epd_server.timeranges` | `TimeRanges` — a day of time ranges, each with an interval; `Week` — groups of days, each with its day of ranges; the slots in them, DST-correct |
| `epd_server.firmware` | `FirmwareStore` — a directory of `<version>.bin`, each with a `<version>.merged.bin` for a USB flash when one is copied in; `ReleaseWatcher` — fill it from a repository's releases; `client_from_headers`, `parse_user_agent`, `is_clean_tag`, `update_applies` — which board an image is an update for |
| `epd_server.mqtt` | `client_log_subscriber` — relay the client's MQTT log topic into Python logging; it keeps trying while the broker cannot be reached |
| `epd_server.certificate` | `ensure_certificate`, `certificate_names` — the self-signed certificate for the HTTPS port, kept for ten years and made anew when its names change |
| `epd_server.install` | `InstallBoard` — a board the install page at `/install` offers; the page writes its firmware and network settings over USB from the browser; `install-firmware.sh` does the same from a terminal |
| `epd_server.network` | `network_settings_file` — the network settings a USB flash writes to a board, as its settings store, made with Espressif's `esp-idf-nvs-partition-gen` |
| `epd_server.source` | `DataSource` — named, lazily fetched datasets; `StaticSource` for constants; `CompositeSource` to merge; `IngestSource` — what a board posted, from a `ReadingsStore` |
| `epd_server.store` | `ReadingsStore` — what a board posts, in SQLite, kept by its `device` and `ts` and read back by time |
| `epd_server.pipeline` | `regenerate(pages, source, only=, force_refresh=)` — fetch what the selected pages need, once each; render; save |
| `epd_server.app` | `DisplayServer(pages, source, schedule, tz, …).run()` — routes, `EPD-Next-*` headers, ingest and query routes, regen loop, client log relay, signals. `align_process_timezone()` |
| `epd_server.headers` | `Wire` — every header name, for one product's prefix |
| `epd_server.compat` | Whether a board's version and the server's work together, by the rule in [docs/protocol.md](../docs/protocol.md) |
| `epd_server.posix_tz` | The server's time zone as a POSIX TZ string, for `EPD-Server-Timezone` |
| `epd_server.logs` | What each board logs over MQTT, kept on disk and read back in order |

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
    https_port=core.server.https_port,
    certificate_dir="data/certificate",
    mqtt=core.mqtt,
).run(once="--once" in sys.argv)
```

`run()` starts the HTTP server on a thread, and with `https_port` an HTTPS
server for the same routes on another, with a self-signed certificate kept
in `certificate_dir`: made at the first start, and made again when its
names change or fewer than 30 days of it are left. Its names are the host
of `client.server_url`, `localhost` and `127.0.0.1`. When the certificate
cannot be made or the port is taken, the server logs it and runs on HTTP
alone. `run()` relays the client's MQTT log topic if enabled, starting once the broker is up and subscribing again after every reconnect, and renders every page on a thread of its own, so the
server answers while it renders. A page asked for before its first render
gets `503` with `Retry-After`. `run()` then sleeps until `regen_lead_seconds`
before each scheduled wake, regenerating that wake's page with a fresh
fetch. `SIGTERM` / `SIGINT` stop it cleanly.

Routes come from the page list — `/<page>.png` for each — plus `/`, which
returns the page list, the schedule and the next wake as JSON. The schedule
is checked against the pages at construction, so a typo in `config.yaml`
fails at startup instead of silently regenerating nothing.

## Readings from a board

A board can post what it measures. `ingest={name: handler}`
gives the server a `POST /<name>` route, and `queries={name: handler}` a
`GET /<name>` one; [docs/protocol.md](../docs/protocol.md) has both. To keep
what arrives, hand the route to a `ReadingsStore` and serve the store to the
pages through an `IngestSource`:

```python
from epd_server import IngestSource, ReadingsStore

store = ReadingsStore("readings.db")
DisplayServer(..., source=IngestSource(store, hours=(24, 72)),
              ingest={"readings": store.add_many})
```

The pages then ask for `latest`, the newest document or None before the
first, and `history_24h` and `history_72h`, the documents of each window,
oldest first. A document is kept by its own `ts`, so one a board held while
the server was down lands where it belongs, and a second copy of the same
`device` and `ts` is ignored. `add_many` writes a batch in one transaction
and answers with which documents were new. `store.prune(before)` deletes
older ones.

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
core.mqtt.enabled, core.mqtt.host, core.mqtt.port, core.mqtt.prefix
core.network.missing(core.mqtt)   # -> the keys a USB flash needs that are not set
```

```yaml
server:
  port: 8080
  https_port: 8443               # the same routes over HTTPS; 0 for none
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
  #   type: timeranges           # or a page at each slot of ranges round the clock,
  #   week:                      # for each group of days, each range running until
  #     - days: [mon, tue, wed, thu, fri, sat, sun]   # the next starts; every: 0 is off
  #       ranges:
  #         - {from: "07:00", every: 300}
  #         - {from: "23:00", every: 0}
  #   order: [morning, evening]  # visited in turn; default: every pool, as listed
  #   reshuffle_hours: 3         # each pool's random start moves this often
image:
  width: 825
  height: 1200
  innerWidth: 825                # content box, <= width
  innerHeight: 1200
  innerAlignX: center            # left | center | right
  innerAlignY: center            # top | center | bottom
client:                          # what the boards this server serves run
  server_url: http://epd.local:8080   # this server, as the boards reach it
  wifi:
    ssid: Home
    password: "8 to 63 characters"
  mqtt_host: epd.local           # the broker, as the boards reach it
  firmware:                      # server-driven client updates
    enabled: false
    dir: firmware                # a directory of <version>.bin; nothing is removed from it
    product: my-display          # the client name a board reports
    # products: [my-display, my-sensor]   # several, each in dir/<product>/
    offer_dev_builds: false      # true offers every developer build the image, not only an older one
mqtt:                            # relay every board's log topic, <prefix>/<board>
  enabled: false
  host: localhost
  port: 1883
  prefix: mqtt/epd
debug: false
```

`client.firmware` lets the server flash the boards it serves. It sits under
`client` because every key in it describes the board rather than this
server. Put an image in `dir` named for its version, `v1.6.0.bin`, and every
board of that product running a different version is offered it on its next
request. The version is the filename, so nothing else has to be written.
With `DisplayServer(version_gate=True)` the offer is the newest image that
can work with the server's own version, not the newest file, so older images
stay. A
relative `dir` is resolved against the directory holding `config.yaml`.
`products` lists several products, each with its images in a subdirectory of
its name.

A board built from a tag takes the update. One built from a working tree
(`v1.5.1-3-gab12cd4`, `-dirty`) takes it only when the image is newer than
its version, so a board tested on a commit moves to the release tagged on it,
and a bench build past the release is not flashed back. A version the server
cannot read (`dev`) is left alone. `offer_dev_builds` offers every developer
build the image. A project passes its own client name as
`default_firmware_product=` to `load_core_config`, so the config file only
needs `enabled: true`.

`server_url`, `wifi` and `mqtt_host` are the board's network settings, which
a USB flash writes. Pass `network=core.network` to `DisplayServer`, beside
`firmware`, which names the products, and it serves them at `/network.bin`.
An enabled firmware block serves each image's `<version>.merged.bin` at
`/firmware.merged.bin` too; see
[docs/protocol.md](../docs/protocol.md#a-usb-flash). A key that is set is
checked at start; one that is not only stops `/network.bin`, which names it.
The install routes read `server.network` at each request, so a project can
replace it while the server runs, as when a person saves new values: they
change only what an install writes, so they need no restart.

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

## The install page

`/install` puts the firmware and the network settings on a board over USB,
from Chrome, Edge, Opera or Firefox, with nothing to install on the
computer. Name the boards it offers, and where a person changes a setting:

```python
from epd_server import InstallBoard

DisplayServer(
    ...,
    firmware=core.firmware,
    network=core.network,
    https_port=core.server.https_port,
    certificate_dir="data/certificate",
    install_boards=[InstallBoard("my-display", "Display", chip="ESP32",
                                 usb_vendor_ids=(0x1A86,))],
    settings_url="settings",     # relative to the server's root
)
```

A browser lets a page use a serial port only over HTTPS, so the page needs
the HTTPS port or a reverse proxy in front of the server. Opened over plain
HTTP, it links to `https_port` by its own number, so map that port to the
same number on the host, as `8443:8443` in Docker. The browser lists only
ports whose USB vendor is in `usb_vendor_ids`: the chip's own USB, or the
board's USB-to-serial chip. The page checks the chip esptool finds against
`chip` before it writes, then writes the merged image at 0x0 and the network
settings after it, and restarts the board.

After the restart the page reads the board's log over the same port and
waits for three lines that EpdClient logs: `wifi connected in` when it joins
Wi-Fi, `reached the server at` at the first answer from an epd server since
boot, and, with MQTT on, `connected to MQTT broker`. It ticks each one off as
it arrives. A line that does not come in time fails the check and names the
setting to look at, or, when the board sent nothing at all, says to
reconnect it: 10 s for any output after the restart, 60 s for Wi-Fi, then
60 s for the server and 30 s for MQTT. The lines are at INFO, so a build
with `LOG_LEVEL` below 4 fails the check on a working board. A board that
joins Wi-Fi with code of its own passes only if it logs these lines; a test
ties the page's lines to the firmware's source.

A project with a layout of its own draws the page in it instead, at a path
of its choice, and the server's `/install` stays for anyone who opens it:

```python
from epd_server.install import config_json

config = server.install_config(root="../")    # the page sits one level down, at /web/install
# in the project's page:
#   <div id="install"></div>
#   <script type="application/json" id="install-config">{config_json(config)}</script>
#   <script type="module" src="../install/install.js"></script>
```

Its page can hold the network settings too, above the boards, since nothing
but an install uses them. Pass `install_url="web/install"` to
`DisplayServer` and `network_here=True` to `install_config`. The page then
says "Add them above" for a missing setting, and "Check the Wi-Fi name and
password above" after a failed check; `/install` and the script send a
person to the install page instead of Settings, and `settings_url` is left
for the HTTPS port. The page reads the config element again at each install,
so a project's page can write fresh values into it after a save without a
reload. While an install runs, the page turns off only the buttons in its
own element.

Every address in the page is relative, so it works behind a reverse proxy at
any path. It writes with [esptool-js](https://github.com/espressif/esptool-js)
0.7.0, kept in `epd_server/static/install` with its licence (Apache-2.0) and
that of pako (MIT and Zlib), which it contains.

### From a terminal

Where the page cannot be used, `install-firmware.sh` does the same install
from a terminal on macOS or Linux (on Windows, Git Bash, untested):

```sh
curl -O http://epd.local:8080/install-firmware.sh
sh install-firmware.sh dock            # firmware and network settings
sh install-firmware.sh dock-network    # network settings only
```

The server serves the script with its own values filled in: its address as
the person reached it, and the boards, the Wi-Fi name and the addresses the
page shows, and where a person sets a missing value: the install page with
`install_url`, else Settings. A board's word is its name in lower case. The script downloads
Espressif's standalone esptool 5.4.0 once, checks it against the checksum
published for it, and keeps it in `$XDG_CACHE_HOME/epd`, or `~/.cache/epd`
when that is not set. It finds the board by the
same USB vendor IDs as the page, writes the merged image and then the
network settings in two esptool commands, since esptool refuses files that
overlap, and follows the board's log for the same three lines. `SERVER`,
`PORT` and `ESPTOOL` override the server's address, the board's port and the
esptool to run. esptool's own output goes to `install-firmware.log` in the
same folder.

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
