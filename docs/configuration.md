# Configuration

The panel and the server are configured separately, and they overlap in only
one place: the address the panel fetches from.

- The **panel** gets its settings from `src/defaults.cpp`, compiled in, with
  three of them overridable from the panel's own storage and all of them
  overridable from an SD card.
- The **server** gets its settings from `config.yaml`, with every key
  overridable by an environment variable.

## Panel: build flags

These go in `build_flags` in `platformio.ini`.

| Flag | What it does |
|---|---|
| `-DARDUINO_INKPLATE10` | Which panel. Also `INKPLATE6`, `INKPLATE5V2`, `INKPLATE2`, and the rest that the Inkplate library supports. Switching panels is only this flag. |
| `-DBOARD_HAS_PSRAM` | The Inkplate has external RAM, and the image buffer needs it. |
| `-DCLIENT_NAME='"my-display"'` | The name the panel introduces itself with. The server matches firmware images against it. Defaults to `EpdClient`. |
| `-DCLIENT_VERSION='"v1.0.0"'` | The version it reports. Defaults to `dev`, which is never offered an update. Normally derived from `git describe` by a script. |
| `-DLOG_LEVEL=4` | 5 is verbose and for development; 4 is normal. |
| `-DUSE_SDCARD` | Read settings from `config.yaml` on the SD card. See below. |

`-DCLIENT_NAME` and `-DCLIENT_VERSION` together become the User-Agent:
`my-display/v1.0.0 (Inkplate10)`. See [the HTTP contract](protocol.md).

## Panel: `src/defaults.cpp`

This file defines the values that `defaults.h` declares. It is the only file
with your credentials in it, so keep it out of git — commit a
`defaults.example.cpp` with placeholders instead, and let your release
pipeline build from that.

| Setting | What it is |
|---|---|
| `serverURL` | The first page to fetch. After that the server names the next one. |
| `serverRetries` | How many further attempts at downloading or drawing. |
| `serverDefaultRefreshSeconds` | How long to sleep when the server has not said — a cold boot, or every attempt failed. |
| `wifiSSID`, `wifiPass` | Your network. |
| `wifiRetries` | How many attempts before giving up on WiFi for this wake. |
| `ntpHost`, `ntpTimezone` | The clock. The timezone is an IANA name, e.g. `Europe/Dublin`. |
| `mqttLogger*` | Optional: publish the panel's log to an MQTT broker, so you can read it without a cable. `mqttLoggerEnabled = false` switches all of it off. |

Three of these — `serverURL`, `wifiSSID` and `wifiPass` — are also kept in
the panel's own storage, so that an image built by CI can still connect. A
value is treated as a placeholder when it is empty, is `XXXX`, or contains
`YOUR_`; a real compiled value always wins and is saved as it passes.
[Updates over the air](ota.md) explains why.

## Panel: settings on an SD card

Build with `-DUSE_SDCARD` and call `applySdConfig(&cfg)` after `loadConfig()`
in your `setup()`. The panel then reads `/config.yaml` from the root of its
SD card, and anything the file sets overrides the compiled value. One build
then serves several panels.

The file names its settings differently from `defaults.cpp`, in groups:

```yaml
server:
  url: http://192.168.1.10:8080/clock.png
  retries: 3
  default_refresh_seconds: 3600
wifi:
  ssid: your-network
  pass: your-password
  retries: 10
ntp:
  host: pool.ntp.org
  timezone: Europe/Dublin
mqtt_logger:
  enabled: false
  broker: localhost
  port: 1883
  clientId: my-display
  topic: mqtt/my-display
  retries: 3
```

The five values under `server.url`, `wifi` and `ntp` are all required; the
file is ignored with a warning if any is missing. The rest fall back to the
compiled value one key at a time.

The SD path needs two more libraries, which are not dependencies of
EpdClient because the card is optional:

```ini
lib_deps =
	symlink://../epd/firmware
	symlink://../epd/firmware/boards/inkplate
	tobozo/YAMLDuino
	bblanchon/ArduinoStreamUtils
```

A missing card, or a card with no `config.yaml`, is not an error: the panel
logs it and carries on with its compiled settings. So the same build works
with and without a card.

## Server: `config.yaml`

`load_core_config()` validates the blocks every epd server has. A project
validates its own keys — an API key, a location — separately.

```yaml
server:
  port: 8080
  timezone: Europe/Dublin      # IANA name; times below are read in this zone
  regen_lead_seconds: 120      # redraw this long before each wake

display:                       # what to show, and when
  pools:
    today: [today.png]
    hourly: [hourly.png]
  schedule:
    type: times                # or: interval
    "08:00:00": today
    "10:00:00": hourly

image:
  width: 825
  height: 1200
  innerWidth: 825              # content box; must be <= width
  innerHeight: 1200
  innerAlignX: center          # left | center | right
  innerAlignY: center          # top | center | bottom

client:                        # what the panels run, not what this server does
  firmware:
    enabled: false
    dir: firmware              # a directory of <version>.bin, newest wins
    product: my-display        # the client name a panel reports
    offer_dev_builds: false
    # source:                  # optional: fill dir from a repository's releases
    #   github: owner/repo
    #   asset: firmware.bin
    #   poll_seconds: 3600
    #   token: ""              # prefer CLIENT_FIRMWARE_SOURCE_TOKEN

mqtt:                          # relay the panel's log topic into this server's log
  enabled: false
  host: localhost
  port: 1883
  topic: mqtt/epd-client

debug: false
```

A **pool** is a list of images shown in turn; a pool of one is just that
image. A `times` schedule names a pool at each time of day. An `interval`
schedule visits pools in order every `every` seconds instead.

`client.firmware` sits under `client` because every key in it describes the
panel rather than the server. A relative `dir` is resolved against the
directory holding `config.yaml`.

### Environment overrides

Every key can be set by an environment variable named after its path, upper
-cased and joined with underscores, and the value is coerced to the type it
replaces:

```
SERVER_PORT=9090
SERVER_TIMEZONE=Europe/London
IMAGE_INNERWIDTH=800
MQTT_ENABLED=true
CLIENT_FIRMWARE_ENABLED=true
CLIENT_FIRMWARE_SOURCE_TOKEN=ghp_…
DEBUG=true
```

The order is always: environment variable, then the YAML value, then the
default. This is how secrets stay out of the file and out of your git
history.

See the [server reference](../server/README.md) for the full table and for
what each module provides.
