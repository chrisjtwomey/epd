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
