# Configuration

The panel and the server are configured separately, and they overlap in
one place: the panel's network settings, the address it fetches from among
them.

- The **panel** gets its settings from `src/defaults.cpp`, compiled in, with
  some of them overridable from the panel's own storage and all of them
  overridable from an SD card. The server can write the ones kept in storage
  over USB ([Updates over the air](ota.md#credentials-and-the-one-usb-flash)).
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
| `-DLOG_LEVEL=4` | 5 is verbose and for development; 4 is normal. The most the build logs, and the level it starts at; `setLogLevel()` lowers it while the board runs. |
| `-DUSE_SDCARD` | Read settings from `config.yaml` on the SD card. See below. |
| `-DEPD_HEADER_PREFIX='"MyDisplay"'` | The prefix of every header name. Defaults to `EPD`. It must match the server's `header_prefix` ([the HTTP contract](protocol.md#the-names)). |

`-DCLIENT_NAME` and `-DCLIENT_VERSION` are what the panel says about
itself on every request, as `EPD-Device` and `EPD-Device-Version`. They also
become its User-Agent, `my-display/v1.0.0 (Inkplate10)`, for your access log.
See [the HTTP contract](protocol.md).

## Panel: `src/defaults.cpp`

This file defines `builtInSettings()`, which returns a `ClientConfig`
(`settings.h`). It is the only file with your credentials in it, so keep it
out of git. Commit a `defaults.example.cpp` with placeholders, and let your
release pipeline build from that.

| Setting | What it is |
|---|---|
| `serverURL` | The first page to fetch. After that the server names the next one. |
| `serverRetries` | How many further attempts at downloading or drawing. |
| `defaultRefreshSeconds` | How long to sleep when the server has not said: a cold boot, or every attempt failed. |
| `wifiSSID`, `wifiPass` | Your network. |
| `wifiRetries` | How long to wait for WiFi on this wake, in seconds: this value plus one. A wait that ends logs why the join failed. |
| `mqttEnabled`, `mqttBroker`, `mqttPort`, `mqttClientID`, `mqttPrefix`, `mqttRetries` | Optional: publish the panel's log to an MQTT broker, so you can read it without a cable. `mqttEnabled = false` turns all of it off. |

`serverURL`, `wifiSSID`, `wifiPass` and the whole MQTT block are also
kept in the panel's own storage, so that an image built by CI can still
connect and still report. A value is treated as a placeholder when it is
empty, is `XXXX`, or contains `YOUR_`; a real compiled value always wins and
is saved as it passes. The MQTT fields travel together, with the broker host
deciding for all of them. [Updates over the air](ota.md) explains why.

## Panel: settings on an SD card

Build with `-DUSE_SDCARD` for a panel that has a card, and call
`applySdConfig(&cfg)` after `loadConfig()` in your `setup()`. The panel then
reads `/config.yaml` from the root of its SD card, and anything the file sets
overrides the compiled value. One build then serves several panels. Leave the
flag out for a panel without a card: looking for one costs about two seconds
at every wake.

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
mqtt_logger:
  enabled: false
  broker: localhost
  port: 1883
  clientId: my-display
  prefix: mqtt/epd
  retries: 3
```

The three values `server.url`, `wifi.ssid` and `wifi.pass` are required; the
file is ignored with a warning if any is missing. The rest fall back to the
compiled value one key at a time.

The SD path needs two more libraries, which are not dependencies of
EpdClient because only a build with the flag uses them:

```ini
lib_deps =
	chrisjtwomey/EpdClient @ ^0.10.1
	chrisjtwomey/EpdBoardInkplate @ ^0.10.1
	tobozo/YAMLDuino
	bblanchon/ArduinoStreamUtils
```

A missing card, or a card with no `config.yaml`, is not an error: the panel
logs a warning and carries on with its compiled settings, so a panel that
loses its card still starts.

## Server: `config.yaml`

`load_core_config()` validates the blocks every epd server has. A project
validates its own keys — an API key, a location — separately.

```yaml
server:
  port: 8080
  https_port: 8443             # the same routes over HTTPS; 0 for none
  timezone: Europe/Dublin      # IANA name; times below are read in this zone
  regen_lead_seconds: 120      # redraw this long before each wake

display:                       # what to show, and when
  pools:
    today: [today.png]
    hourly: [hourly.png]
  schedule:
    type: times                # or: timeranges
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
  server_url: http://epd.local:8080   # this server, as the panels reach it
  wifi:
    ssid: Home
    password: "8 to 63 characters"
  mqtt_host: epd.local         # the broker, as the panels reach it
  firmware:
    enabled: false
    dir: firmware              # a directory of <version>.bin; see Updates over the air
    product: my-display        # the client name a panel reports
    # products: [my-display, my-sensor]   # several, each in dir/<product>/
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
  prefix: mqtt/epd               # boards log to <prefix>/<board>

debug: false
```

A **pool** is a list of images shown in turn; a pool of one is just that
image. A `times` schedule names a pool at each time of day. A `timeranges`
schedule visits the pools in `order` at each slot of its `week` instead:
groups of days, each with its own time ranges.

```yaml
  schedule:
    type: timeranges
    week:
      - days: [mon, tue, wed, thu, fri]
        ranges:                # each runs until the next starts, the last past midnight
          - {from: "07:00", every: 300}
          - {from: "23:00", every: 0}  # 0: no page changes until 07:00
      - days: [sat, sun]
        ranges:
          - {from: "09:00", every: 600}
    order: [today, hourly]     # default: every pool, as listed
```

Each day of the week is in exactly one group; one group of all seven is the
same schedule every day. A day stands alone: before its first start, its own
last range runs, not the day before's, so a day's ranges say all that
happens on it.

A range's slots fall a whole number of its intervals after its start, so a
range has a slot at its start: from 08:30 every 1200 gives 08:30, 08:50,
09:10 and so on, and from 07:00 every 300 gives :00, :05, :10. A range starts
when it says, whatever its interval. One range from 00:00 is a page every so
often all day. A group has at most
8 ranges, and one range in the week must have an interval.

`server.https_port`, 8443 unless set, serves every route over HTTPS as
well, with a self-signed certificate that the server makes and keeps: a
browser lets a page use a serial port only over HTTPS, or on localhost, and
the install page at `/install` uses one. In Docker, map it to the same
number on the host: the page opened over plain HTTP links to it by that
number. The
browser warns about the certificate, since nobody vouches for it. The port
must differ from `server.port`. Set it to 0 behind a reverse proxy that has
a certificate of its own. A project passes it to `DisplayServer` with a
directory for the certificate. When the certificate cannot be made or the
port is taken, the server logs it and runs on HTTP alone.

`client.firmware` sits under `client` because every key in it describes the
panel rather than the server. A relative `dir` is resolved against the
directory holding `config.yaml`.

`server_url`, `wifi` and `mqtt_host` are what a USB flash writes to a panel,
as its [network settings](ota.md#credentials-and-the-one-usb-flash). They
describe the network as the panel sees it, which in Docker is not what the
server sees: `mqtt.host` stays the server's own way to its broker.
`mqtt.enabled`, `mqtt.port` and `mqtt.prefix` serve both. The server checks
each key that is set:

- `server_url` is `http://host` or `http://host:port`, with nothing after
  it. The server adds the first of its pages, for a panel's first fetch; a
  board that only posts keeps the host and the port.
- `wifi.ssid` is 32 bytes or fewer.
- `wifi.password` is 8 to 63 characters. A panel cannot join an open
  network from its stored settings.
- `mqtt_host` is a host name or an address alone.
- An SSID or a password is text: quote one that YAML would read as a number
  or as true or false.

A key that is not set does not stop the server; it only stops the network
settings from being served. `mqtt_host` is needed only while `mqtt.enabled`
is true.

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
CLIENT_WIFI_PASSWORD=…
DEBUG=true
```

The order is always: environment variable, then the YAML value, then the
default. This is how secrets stay out of the file and out of your git
history.

See the [server reference](../server/README.md) for the full table and for
what each module provides.
