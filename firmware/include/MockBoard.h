#ifndef __MOCKBOARD_H__
#define __MOCKBOARD_H__

#include "IBoard.h"
#include <string.h>

/**
 * Test double for IBoard.
 *
 * All methods are no-ops or return configurable values. Call-tracking fields
 * let tests assert which methods were called and with what arguments.
 *
 * Usage:
 *   MockBoard mock;
 *   mock.epochReturn = 1000;
 *   IBoard& board = mock;
 *   sleep_for(3600);
 *   TEST_ASSERT_EQUAL(4600, mock.lastAlarmEpoch);
 */
class MockBoard : public IBoard {
public:
    MockBoard()
        : epochReturn(0),
          batteryReturn(4.0),
          panelTempReturn(25),
          widthReturn(1200),
          heightReturn(825),
          drawBitmapReturn(true),
          drawPngReturn(true),
          sdCardInitReturn(true),
          lastAlarmEpoch(0),
          lastSetEpoch(0),
          rtcSetEpochCalled(false),
          rtcSetAlarmEpochCalled(false),
          enableWakeOnRtcAlarmCalled(false),
          rtcClearAlarmFlagCalled(false),
          rtcGetDataCalled(false),
          displayCount(0),
          clearDisplayCount(0),
          drawBitmapBuf(nullptr),
          drawBitmapX(0),
          drawBitmapY(0),
          drawBitmapW(0),
          drawBitmapH(0),
          drawBitmapInvert(false),
          lastCursorX(0),
          lastCursorY(0),
          lastFont(nullptr) {}

    // -------------------------------------------------------------------------
    // Configurable return values
    // -------------------------------------------------------------------------

    time_t   epochReturn;
    double   batteryReturn;
    int      panelTempReturn;
    int16_t  widthReturn;
    int16_t  heightReturn;
    bool     drawBitmapReturn;
    bool     drawPngReturn;
    bool     sdCardInitReturn;

    // -------------------------------------------------------------------------
    // Call tracking
    // -------------------------------------------------------------------------

    time_t      lastAlarmEpoch;
    time_t      lastSetEpoch;
    bool        rtcSetEpochCalled;
    bool        rtcSetAlarmEpochCalled;
    bool        enableWakeOnRtcAlarmCalled;
    bool        rtcClearAlarmFlagCalled;
    bool        rtcGetDataCalled;
    int         displayCount;
    int         clearDisplayCount;

    // drawBitmap tracking (used to verify battery icon selection)
    uint8_t*    drawBitmapBuf;
    int         drawBitmapX;
    int         drawBitmapY;
    int         drawBitmapW;
    int         drawBitmapH;
    bool        drawBitmapInvert;

    // Text / cursor tracking
    int16_t     lastCursorX;
    int16_t     lastCursorY;
    FontHandle  lastFont;

    // -------------------------------------------------------------------------
    // IBoard implementation
    // -------------------------------------------------------------------------

    const char* deviceName() const override { return "MockBoard"; }
    void begin() override {}
    void setRotation(uint8_t) override {}

    int16_t getWidth()  const override { return widthReturn; }
    int16_t getHeight() const override { return heightReturn; }

    void clearDisplay() override { ++clearDisplayCount; }
    void display()      override { ++displayCount; }

    bool drawPngFromBuffer(uint8_t*, int32_t, int, int, bool, bool) override {
        return drawPngReturn;
    }
    bool drawPngFromSd(const char*, int, int, bool, bool) override {
        return drawPngReturn;
    }
    bool drawBitmap(uint8_t* buf, int x, int y, int w, int h,
                    uint16_t, uint16_t) override {
        drawBitmapBuf    = buf;
        drawBitmapX      = x;
        drawBitmapY      = y;
        drawBitmapW      = w;
        drawBitmapH      = h;
        return drawBitmapReturn;
    }

    // Everything print() was handed this run, in order, one per line. A test
    // that cares what reached the panel reads this.
    String printedText;

    void setFont(FontHandle font) override { lastFont = font; }
    void setTextSize(uint8_t)     override {}
    void setTextColor(uint16_t)   override {}
    void setTextWrap(bool)        override {}

    void getTextBounds(const char*, int16_t, int16_t,
                       int16_t* x1, int16_t* y1,
                       uint16_t* w, uint16_t* h) override {
        if (x1) *x1 = 0;
        if (y1) *y1 = 0;
        if (w)  *w  = 0;
        if (h)  *h  = 10;
    }

    void setCursor(int16_t x, int16_t y) override {
        lastCursorX = x;
        lastCursorY = y;
    }

    void print(const char* str)   override { printedText += str; printedText += "\n"; }
    void print(const String& str) override { print(str.c_str()); }

    void fillRect(int16_t, int16_t, int16_t, int16_t, uint16_t) override {}

    double readBattery() override { return batteryReturn; }
    int readPanelTemperature() override { return panelTempReturn; }

    void   rtcGetData()          override { rtcGetDataCalled = true; }
    time_t rtcGetEpoch()         override { return epochReturn; }
    void   rtcClearAlarmFlag()   override { rtcClearAlarmFlagCalled = true; }
    void   rtcSetAlarmEpoch(time_t epoch) override {
        rtcSetAlarmEpochCalled = true;
        lastAlarmEpoch = epoch;
    }
    void   rtcSetEpoch(time_t epoch) override {
        rtcSetEpochCalled = true;
        lastSetEpoch = epoch;
    }
    void   enableWakeOnRtcAlarm() override { enableWakeOnRtcAlarmCalled = true; }

#if defined(USE_SDCARD)
    bool sdCardInit()  override { return sdCardInitReturn; }
    void sdCardSleep() override {}

    bool sdWriteFile(const char*, const uint8_t*, size_t) override {
        return sdWriteFileReturn;
    }
    size_t sdReadFile(const char*, uint8_t* buf, size_t maxLen) override {
        if (!sdReadFileContent || !buf || maxLen == 0) return 0;
        size_t len = strlen(sdReadFileContent);
        if (len > maxLen - 1) len = maxLen - 1;
        memcpy(buf, sdReadFileContent, len);
        buf[len] = '\0';
        return len;
    }

    // Configurable SD behaviour (only present in USE_SDCARD builds).
    bool        sdWriteFileReturn  = true;
    const char* sdReadFileContent  = nullptr;  // nullptr = file absent
#endif
};

#endif // __MOCKBOARD_H__
