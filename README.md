# epd

Reusable building blocks for battery-powered e-paper dashboards: an ESP32
client that draws a server-rendered PNG, and (from step 3) a Python server that
renders HTML pages to PNG on a schedule.

Extracted from [inkplate10-weather-cal](https://github.com/chrisjtwomey/inkplate10-weather-cal),
which is now a thin consumer of these libraries.

## The idea

A project built on epd supplies only three things:

1. **Which board** — an `IBoard` implementation (or one that ships here).
2. **Which pages** — the HTML the server renders.
3. **Which data** — where the page content comes from.

Everything else — wake scheduling, WiFi, HTTP, back-off, battery monitoring,
deep sleep, error banners, image capture — comes from the kit.

## The wire contract

The client and server are joined by one small HTTP exchange:

```
GET /<page>.png
  200 image/png
  X-Next-Refresh-Seconds: 7200         ← client sleeps this many seconds
  X-Next-URL: http://host/hourly.png   ← client fetches this next
```

The server is the single source of truth for *when* to wake and *what* to show.
The client does no timezone maths and holds no schedule of its own.

Every request carries the client's identity, so the server knows what each
board runs:

```
User-Agent: inkplate10-weather-cal/v1.5.1 (Inkplate10)
```

A server that holds a newer image for that product adds two headers to the
page response, and serves the image on a route of its own:

```
GET /<page>.png
  X-Firmware-Version: v1.6.0
  X-Firmware-URL: http://host/firmware.bin

GET /firmware.bin
  200 application/octet-stream, Content-Length, x-MD5
  304 when the request's x-ESP32-version is the version held
  404 when the server holds no image
```

The board fetches the image only after it has drawn its page, so a failed
update costs nothing on the panel.

## Firmware

| Library | What it is |
|---|---|
| `firmware/` — **EpdClient** | The hardware-agnostic client: `run_app()`, WiFi, HTTP download, back-off, battery, deep sleep, display helpers. Depends only on `IBoard`. |
| `firmware/boards/inkplate/` — **EpdBoardInkplate** | `IBoard` for Soldered / e-radionica Inkplate panels. Separate so projects on other hardware never pull in InkplateLibrary. |

### Using it

This repo holds **two** libraries in one tree. A `lib_deps` git URL can only
address a repository root, so consumers reach them one of two ways:

**Local checkout** (what `inkplate10-weather-cal` uses today):

```ini
lib_deps =
	symlink://../epd/firmware
	symlink://../epd/firmware/boards/inkplate
```

**Published packages** — after `pio pkg publish` from each library directory:

```ini
lib_deps =
	chrisjtwomey/EpdClient@^0.1.0
	chrisjtwomey/EpdBoardInkplate@^0.1.0
```

A full environment:

```ini
[env:release]
platform = espressif32
framework = arduino
board = esp32dev
lib_deps =
	symlink://../epd/firmware
	symlink://../epd/firmware/boards/inkplate
build_flags =
	-DARDUINO_INKPLATE10          ; or -DARDUINO_INKPLATE5V2, etc.
	-DBOARD_HAS_PSRAM
	-DCLIENT_NAME='"my-display"'   ; product token of the User-Agent
	-DCLIENT_VERSION='"v1.0.0"'
	-DLOG_LEVEL=4
```

Every download carries `User-Agent: my-display/v1.0.0 (Inkplate10)`: the
name, the version, and the board's `deviceName()`. Without `CLIENT_NAME`
the product is `EpdClient`; without `CLIENT_VERSION` the version is `dev`.

An awake client can send data back with `postJson(url, userAgent, body)`,
which returns the HTTP status. The server side is `DisplayServer(ingest=
{"readings": handler})`: `POST /readings` parses a JSON object and hands it
to the handler.

Enabling `-DUSE_SDCARD` also needs `tobozo/YAMLDuino` and
`bblanchon/ArduinoStreamUtils` in your `lib_deps`: the YAML config path is
optional, so those are not hard dependencies of EpdClient.

Your project supplies two files:

**`src/main.cpp`**

```cpp
#include "InkplateBoard.h"
#include "app.h"

static InkplateBoard inkplateBoard;
IBoard& board = inkplateBoard;   // EpdClient links against this

void setup() { run_app(); }
void loop()  {}
```

**`src/defaults.cpp`** — definitions for the symbols `defaults.h` declares
(server URL, WiFi credentials, NTP host, MQTT logging).

### Updating over the air

A board with a server that holds firmware updates itself. The page response
offers a version and a URL, and the client fetches the image after it has
drawn, so an update never holds up the panel. A failed update ends the wake
the way it would have ended anyway, and the next wake tries again.

The ESP32 has two app slots. The image is written to the idle one and the
board restarts into it **on trial**: the bootloader takes it back unless the
application says it works. `run_app()` says so only after a page is on the
panel, and rolls back on any failure before that. Confirming comes before
taking the next offer, since a write to the idle slot is refused while an
image is pending.

An image built by a release pipeline cannot carry a WiFi password, so the
server URL, the SSID and the password come from the board's own store
(`Preferences`, namespace `epd`) whenever the running image has only the
placeholders `defaults.example.cpp` ships. A build flashed over USB with
real values writes them there, which provisions the board for every image
that arrives later. So one USB flash is needed, and only one.

Nothing in `defaults.cpp` else is stored: the rest is code, and comes from
the image.

To force an update, press RST. The board boots from the top — WiFi, fetch,
draw, then the update check — so an offered image is applied within a
minute. A reset during the write is safe, because the boot pointer moves
only when the write completes.

### Supporting other hardware

Subclass `IBoard`, implement every pure-virtual method, and assign your
instance to the global `board` reference. See [docs/custom-board.md](docs/custom-board.md).

Switching between Inkplate models is only a build flag — `InkplateBoard` wraps
whichever panel `InkplateLibrary` compiles for.

### Tests

The client's unit and integration tests live with the code they cover:

```sh
cd firmware
pio test -e native              # pure helpers: back-off, battery, header parsing
pio test -e native_mock         # display + sleep against MockBoard
pio test -e native_integration  # the full run_app() control flow
```

`platformio.ini` here is a host-only test project. It is excluded from the
published library, so consumers never see it.

## Server — `server/`

The `epd_server` Python package: config resolution, plugin registry, disk cache, `Page` (HTML → quantised PNG), scheduling maths, and the MQTT client-log relay. See [server/README.md](server/README.md).

## License

MIT
