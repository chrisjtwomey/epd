# Integrating a custom board

EpdClient reaches the hardware only through the `IBoard` interface
(`firmware/include/IBoard.h`). The Inkplate driver is a library of its own,
`EpdBoardInkplate` (`firmware/boards/inkplate/`), so a project on other hardware
never pulls in the Inkplate library.

To support another e-paper board:

1. Subclass `IBoard`, and implement each pure-virtual method.
2. Give your board to `epdBegin()` in your `setup()`.

EpdClient runs only on the ESP32 (`platforms: espressif32` in its
`library.json`), so your board must have one.

## 1. Understand the interface

### Lifecycle

| Method | Purpose |
|---|---|
| `deviceName() const` | Human-readable device label used in boot log lines. |
| `begin()` | One-time hardware initialisation, called at startup before any other method. |
| `setRotation(r)` | Set display rotation 0–3 (Adafruit GFX convention: 0 = portrait, 1 = landscape, …). |
| `getWidth() const` | Physical panel width in pixels **before** rotation is applied. |
| `getHeight() const` | Physical panel height in pixels **before** rotation is applied. |

### Display output

| Method | Purpose |
|---|---|
| `clearDisplay()` | Erase the in-memory frame buffer to white. |
| `display()` | Flush the in-memory frame buffer to the physical panel. |
| `setBlackAndWhite(on)` | Optional; the base class ignores it. Draw in black and white, or in greys. Colour values are the mode's own. `InkplateBoard` switches the library's mode, since its partial updates work only in black and white. |
| `partialDisplay()` | Optional; the base class calls `display()`. Push only the pixels that changed, without the flashing of a full refresh. |

### Image drawing (into the frame buffer)

| Method | Purpose |
|---|---|
| `drawPngFromBuffer(buf, len, x, y, dither, invert)` | Decode a PNG from a byte buffer and render it at `(x, y)`. Returns `true` on success. |
| `drawPngFromSd(path, x, y, dither, invert)` | Decode a PNG from an SD-card file and render it at `(x, y)`. Returns `true` on success. You must implement it, but EpdClient calls it only when `USE_SDCARD` is defined. |
| `drawBitmap(buf, x, y, w, h, fg, bg)` | Draw a raw 1-bit bitmap at `(x, y)`. Used for battery status icons. Returns `true` on success. |

### Text / GFX primitives

These mirror the [Adafruit GFX](https://github.com/adafruit/Adafruit-GFX-Library) API so that drivers backed by a compatible library can delegate calls directly.

| Method | Notes |
|---|---|
| `setFont(font)` | `FontHandle` is `const void*`; cast to `const GFXfont*` for Adafruit GFX. |
| `setTextSize(s)` | Scale factor (1 = native). |
| `setTextColor(c)` | 16-bit colour value. |
| `setTextWrap(wrap)` | Enable/disable line wrapping. |
| `getTextBounds(str, x, y, x1, y1, w, h)` | Write bounding box of `str` into the out-params. |
| `setCursor(x, y)` | Move the text cursor. |
| `print(str)` | Draw a null-terminated string at the current cursor. |
| `print(str)` | Overload accepting `const String&`. |
| `fillRect(x, y, w, h, color)` | Fill a solid rectangle. Used for the banner background in `displayMessage`. |

### Battery

| Method | Notes |
|---|---|
| `readBattery()` | Return the current battery voltage in volts as a `double`. |

### Panel

| Method | Notes |
|---|---|
| `readPanelTemperature()` | The temperature at the panel's power controller, in whole °C. It reads the board, not the room: a diagnostic. |

### RTC

The firmware relies entirely on the hardware RTC for deep-sleep scheduling.
No NTP or timezone arithmetic is required on the client — the server
sends an `EPD-Next-Display-Refresh-Seconds` header and the client simply adds that
offset to the current epoch when setting the alarm. The RTC holds UTC, set
from the server's clock with each page.

| Method | Notes |
|---|---|
| `rtcGetData()` | Read hardware RTC registers into memory. Called once at startup. |
| `rtcGetEpoch()` | Return the current Unix timestamp held in the RTC. |
| `rtcSetEpoch(epoch)` | Write `epoch` to the RTC. Called with the server's clock, from `keepServerTime()`, so the RTC stays accurate across deep sleep. |
| `rtcClearAlarmFlag()` | Clear any pending alarm interrupt flag (called on `ESP_SLEEP_WAKEUP_EXT0`). |
| `rtcSetAlarmEpoch(epoch)` | Program the RTC alarm to fire at `epoch`. All alarm-match mode details are encapsulated inside the implementation. |
| `enableWakeOnRtcAlarm()` | Arm the deep-sleep wake source the RTC alarm drives. The alarm reaches the SoC on a board-specific pin, so the pin and wake mode belong here. `InkplateBoard` calls `esp_sleep_enable_ext0_wakeup(GPIO_NUM_39, 0)`. |

### GPIO expander

| Method | Notes |
|---|---|
| `writeExpanderPin(pin, high)` | Optional; the base class returns `false`, meaning the board wrote nothing. Implement it when the board has an IO expander whose free pins a project needs — `InkplateBoard` drives the PCAL6416A. A `true` return says the write was issued, not that the pin moved. |

### SD card (`USE_SDCARD` only)

These methods are compiled only when the `USE_SDCARD` build flag is set.

| Method | Notes |
|---|---|
| `sdCardInit()` | Initialise the SD card. Returns `true` on success. |
| `sdCardSleep()` | Put the SD card into low-power sleep before deep sleep. |
| `sdWriteFile(path, buf, len)` | Write `len` bytes to `path`, replacing any existing file. Returns `true` on success. Used to cache the downloaded image. |
| `sdReadFile(path, buf, maxLen)` | Read up to `maxLen` bytes from `path`. Returns the byte count, or `0` if the file is missing or empty. Used to load `config.yaml`. |

> **Why file I/O is on `IBoard`:** storage is reached only through
> `sdWriteFile` / `sdReadFile`, so the client library never names a concrete SD
> type and never depends on a specific board driver. `InkplateBoard` still
> exposes `getSdFat()` for direct `SdFat` access, but nothing in `EpdClient`
> uses it — your driver is free to back these two methods with any filesystem.
>
> `sdReadFile` should null-terminate the buffer when the data fits, so callers
> can treat a text file such as `config.yaml` as a C string.

---

## 2. Create your driver

Add your header and implementation files anywhere the build system can find
them — `include/` and `src/` are the simplest choices.

**`include/MyBoard.h`**

```cpp
#pragma once
#include "IBoard.h"

class MyBoard : public IBoard {
public:
    MyBoard();

    // Lifecycle
    const char* deviceName() const override;
    void        begin()              override;
    void        setRotation(uint8_t r) override;
    int16_t     getWidth()  const    override;
    int16_t     getHeight() const    override;

    // Display output
    void clearDisplay() override;
    void display()      override;

    // Image drawing
    bool drawPngFromBuffer(uint8_t* buf, int32_t len,
                           int x, int y,
                           bool dither, bool invert) override;
    bool drawPngFromSd(const char* path,
                       int x, int y,
                       bool dither, bool invert) override;
    bool drawBitmap(uint8_t* buf,
                    int x, int y, int w, int h,
                    uint16_t fg, uint16_t bg) override;

    // Text / GFX
    void setFont(FontHandle font)                   override;
    void setTextSize(uint8_t s)                     override;
    void setTextColor(uint16_t c)                   override;
    void setTextWrap(bool wrap)                     override;
    void getTextBounds(const char* str,
                       int16_t x,  int16_t y,
                       int16_t* x1, int16_t* y1,
                       uint16_t* w, uint16_t* h)   override;
    void setCursor(int16_t x, int16_t y)            override;
    void print(const char* str)                     override;
    void print(const String& str)                   override;
    void fillRect(int16_t x, int16_t y,
                  int16_t w, int16_t h,
                  uint16_t color)                   override;

    // Battery
    double readBattery() override;

    // Panel
    int    readPanelTemperature() override;

    // RTC
    void   rtcGetData()                    override;
    time_t rtcGetEpoch()                   override;
    void   rtcSetEpoch(time_t epoch)       override;
    void   rtcClearAlarmFlag()             override;
    void   rtcSetAlarmEpoch(time_t epoch)  override;
    void   enableWakeOnRtcAlarm()          override;

#if defined(USE_SDCARD)
    bool   sdCardInit()  override;
    void   sdCardSleep() override;
    bool   sdWriteFile(const char* path, const uint8_t* buf, size_t len) override;
    size_t sdReadFile(const char* path, uint8_t* buf, size_t maxLen) override;
#endif

private:
    // Your hardware driver instance goes here, e.g.:
    // MyEpaperDriver _driver;
};
```

Implement each method in `src/MyBoard.cpp`, around your hardware driver.
`firmware/boards/inkplate/src/InkplateBoard.cpp` shows what each method does
for the Inkplate.

---

## 3. Give your board to `epdBegin()`

`src/main.cpp` is the only file that changes:

```cpp
// The Inkplate
#include "EpdBoardInkplate.h"
static InkplateBoard board;

// Your board
#include "MyBoard.h"
static MyBoard board;

void setup() {
    epdBegin(board);    // before any other EpdClient call
    ...
}
```

All of EpdClient reaches the board through `epdBoard()`, which returns the board
that `epdBegin()` was given. Nothing else changes.

---

## 4. Update `platformio.ini`

Add your driver's library to `lib_deps`, beside EpdClient. Leave
`EpdBoardInkplate` out, so that the Inkplate library is not pulled in:

```ini
lib_deps =
    chrisjtwomey/EpdClient @ ^0.10.2
    your-vendor/YourLibrary@^1.0.0
```

---

## 5. Testing without hardware

`MockBoard` (`firmware/include/MockBoard.h`) is an `IBoard` that records what
it was asked to do, and drives no panel. Each method is a no-op that you can
set up, with fields that record the calls.

- epd's own `native_mock` tests use it. So does a project's test of its own
  wake ([testing.md](testing.md)).
- If you add a method to `IBoard`, add a matching no-op to `MockBoard`, or the
  host tests do not compile.
- To run epd's own host tests, see [CONTRIBUTING.md](../CONTRIBUTING.md#tests).
