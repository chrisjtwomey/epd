#include "InkplateBoard.h"

#include <new>
#include <string.h>

#include <esp_heap_caps.h>

#include <PNGdec.h>

#include "frame_rows.h"

// Where the Inkplate's PCF85063A RTC drives its interrupt line.
static const gpio_num_t kRtcAlarmWakePin = GPIO_NUM_39;

InkplateBoard::InkplateBoard() : _inkplate(INKPLATE_3BIT) {}

// -----------------------------------------------------------------------------
// Lifecycle
// -----------------------------------------------------------------------------

const char* InkplateBoard::deviceName() const {
    // The board define the Inkplate library was compiled with. Adding a panel
    // here is cosmetic: it only changes the boot log.
#if defined(ARDUINO_INKPLATE10)
    return "Inkplate10";
#elif defined(ARDUINO_INKPLATE5V2)
    return "Inkplate5V2";
#elif defined(ARDUINO_INKPLATE5)
    return "Inkplate5";
#elif defined(ARDUINO_INKPLATE6PLUS)
    return "Inkplate6PLUS";
#elif defined(ARDUINO_INKPLATE6FLICK)
    return "Inkplate6FLICK";
#elif defined(ARDUINO_INKPLATE6)
    return "Inkplate6";
#elif defined(ARDUINO_INKPLATE4)
    return "Inkplate4";
#elif defined(ARDUINO_INKPLATE2)
    return "Inkplate2";
#else
    return "Inkplate";
#endif
}

void InkplateBoard::begin() {
    _inkplate.begin();
}

void InkplateBoard::setRotation(uint8_t r) {
    _inkplate.setRotation(r);
}

int16_t InkplateBoard::getWidth() const {
    return E_INK_WIDTH;
}

int16_t InkplateBoard::getHeight() const {
    return E_INK_HEIGHT;
}

// -----------------------------------------------------------------------------
// Display output
// -----------------------------------------------------------------------------

void InkplateBoard::clearDisplay() {
    _inkplate.clearDisplay();
}

void InkplateBoard::display() {
    _inkplate.display();
}

void InkplateBoard::setBlackAndWhite(bool on) {
    _inkplate.selectDisplayMode(on ? INKPLATE_1BIT : INKPLATE_3BIT);
}

void InkplateBoard::partialDisplay() {
    if (_inkplate.getDisplayMode() == INKPLATE_1BIT)
        _inkplate.partialUpdate();
    else
        _inkplate.display();
}

// -----------------------------------------------------------------------------
// Image drawing
// -----------------------------------------------------------------------------

// In black and white, the library's undithered PNG path writes each pixel's
// 3-bit grey as its colour, which draws black as white and every other grey
// as black. Dithering maps each pixel to black or white, and leaves an image
// that is already black and white as it is.
static bool pngDither(Inkplate& inkplate, PngDraw options) {
    return pngDrawHas(options, PngDraw::Dither) || inkplate.getDisplayMode() == INKPLATE_1BIT;
}

// The boards whose drivers keep a 3-bit frame buffer that FrameRows writes as
// their drawPixel() does (InkplateLibrary 11.2.1).
#if defined(ARDUINO_INKPLATE10) || defined(ARDUINO_INKPLATE10V2) || \
    defined(ARDUINO_INKPLATE5V2) || defined(ARDUINO_INKPLATE6) || defined(ARDUINO_INKPLATE6PLUS)
#define EPD_GREY_PNG_ROWS 1
#endif

#if defined(EPD_GREY_PNG_ROWS)
// How many decoded rows are written to the frame buffer together.
static const int kRowsPerBlock = 16;

// One page's rows on their way into the frame buffer, gathered into blocks in
// internal RAM: the frame buffer is in PSRAM, and on a portrait page a single
// row would touch a different line of it with every pixel.
struct PngRows {
    FrameRows rows;
    int x, y;
    uint8_t* block;
    int width;
    int held;
    int firstRow;

    void flush() {
        if (held) rows.writeGreyRows(x, y + firstRow, block, width, held, width);
        held = 0;
    }
};

static int drawPngRow(PNGDRAW* draw) {
    PngRows* page = static_cast<PngRows*>(draw->pUser);
    if (page->held == 0) page->firstRow = draw->y;
    memcpy(page->block + page->held * page->width, draw->pPixels, page->width);
    if (++page->held == kRowsPerBlock) page->flush();
    return 1;
}

// An 8-bit grey PNG, decoded a row at a time straight into the frame buffer:
// the library's path decodes it a byte at a time and draws it a pixel at a
// time, which takes seconds for a page. The decoder's state is about 45 KB,
// most of it the inflate window, so it lives on the heap: in PSRAM.
static bool drawGreyPngRows(Inkplate& inkplate, const uint8_t* buf, int32_t len, int x, int y) {
    static PNG* png = new (std::nothrow) PNG();
    if (!png) return false;
    if (png->openRAM(const_cast<uint8_t*>(buf), len, drawPngRow) != PNG_SUCCESS) return false;
    bool drawn = false;
    if (png->getPixelType() == PNG_PIXEL_GRAYSCALE && png->getBpp() == 8) {
        const int width = png->getWidth();
        uint8_t* block = static_cast<uint8_t*>(
            heap_caps_malloc((size_t)kRowsPerBlock * width, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
        if (block) {
            PngRows page{{inkplate.DMemory4Bit, E_INK_WIDTH, E_INK_HEIGHT, inkplate.getRotation()},
                         x, y, block, width, 0, 0};
            drawn = png->decode(&page, 0) == PNG_SUCCESS;
            if (drawn) page.flush();
            heap_caps_free(block);
        }
    }
    png->close();
    return drawn;
}
#endif

// In 3-bit greys and undithered, the library ignores options' Invert, and so
// does the row path.
bool InkplateBoard::drawPngFromBuffer(const uint8_t* buf, int32_t len,
                                      int x, int y, PngDraw options) {
    const bool dither = pngDither(_inkplate, options);
#if defined(EPD_GREY_PNG_ROWS)
    if (!dither && drawGreyPngRows(_inkplate, buf, len, x, y)) return true;
#endif
    // The library only reads the buffer, but takes it as non-const.
    return _inkplate.image.drawPngFromBuffer(const_cast<uint8_t*>(buf), len, x, y, dither,
                                             pngDrawHas(options, PngDraw::Invert));
}

bool InkplateBoard::drawBitmap(const uint8_t* buf,
                               int x, int y, int w, int h,
                               uint16_t fg, uint16_t bg) {
    return _inkplate.image.draw(buf, x, y, w, h, fg, bg);
}

// -----------------------------------------------------------------------------
// Text / GFX
// -----------------------------------------------------------------------------

void InkplateBoard::setFont(FontHandle font) {
    _inkplate.setFont(reinterpret_cast<const GFXfont*>(font));
}

void InkplateBoard::setTextSize(uint8_t s) {
    _inkplate.setTextSize(s);
}

void InkplateBoard::setTextColor(uint16_t c) {
    _inkplate.setTextColor(c);
}

void InkplateBoard::setTextWrap(bool wrap) {
    _inkplate.setTextWrap(wrap);
}

void InkplateBoard::getTextBounds(const char* str,
                                  int16_t x, int16_t y,
                                  int16_t* x1, int16_t* y1,
                                  uint16_t* w, uint16_t* h) {
    _inkplate.getTextBounds(str, x, y, x1, y1, w, h);
}

void InkplateBoard::setCursor(int16_t x, int16_t y) {
    _inkplate.setCursor(x, y);
}

void InkplateBoard::print(const char* str) {
    _inkplate.print(str);
}

void InkplateBoard::print(const String& str) {
    _inkplate.print(str);
}

void InkplateBoard::fillRect(int16_t x, int16_t y,
                             int16_t w, int16_t h,
                             uint16_t color) {
    _inkplate.fillRect(x, y, w, h, color);
}

// -----------------------------------------------------------------------------
// Battery
// -----------------------------------------------------------------------------

double InkplateBoard::readBattery() {
    return _inkplate.readBattery();
}

int InkplateBoard::readPanelTemperature() {
    return _inkplate.readTemperature();
}

// -----------------------------------------------------------------------------
// RTC
// -----------------------------------------------------------------------------

time_t InkplateBoard::rtcGetEpoch() {
    return _inkplate.rtc.getEpoch();
}

void InkplateBoard::rtcSetEpoch(time_t epoch) {
    _inkplate.rtc.setEpoch(epoch);
}

void InkplateBoard::rtcClearAlarmFlag() {
    _inkplate.rtc.clearAlarmFlag();
}

void InkplateBoard::rtcSetAlarmEpoch(time_t epoch) {
    // RTC_ALARM_MATCH_DHHMMSS is the Inkplate-specific alarm match mode;
    // hidden here so callers depend only on the IBoard interface.
    _inkplate.rtc.setAlarmEpoch(epoch, RTC_ALARM_MATCH_DHHMMSS);
}

void InkplateBoard::enableWakeOnRtcAlarm() {
    // Kept here rather than in sleep_utils so other boards can use their own
    // pin and wake source.
    esp_sleep_enable_ext0_wakeup(kRtcAlarmWakePin, 0);
}

// -----------------------------------------------------------------------------
// SD card
// -----------------------------------------------------------------------------

#if defined(USE_SDCARD)
bool InkplateBoard::sdCardInit() {
    return _inkplate.sdCardInit();
}

void InkplateBoard::sdCardSleep() {
    _inkplate.sdCardSleep();
}

bool InkplateBoard::drawPngFromSd(const char* path,
                                  int x, int y, PngDraw options) {
    return _inkplate.image.drawPngFromSd(path, x, y, pngDither(_inkplate, options),
                                         pngDrawHas(options, PngDraw::Invert));
}

bool InkplateBoard::sdWriteFile(const char* path, const uint8_t* buf, size_t len) {
    SdFat& sd = _inkplate.getSdFat();

    // Use SdFile with raw SdFat open flags rather than FILE_WRITE: FS.h
    // redefines FILE_WRITE to "w" (const char*), which SdFile won't accept.
    SdFile file;
    file.open(&sd, path, O_WRITE | O_CREAT | O_TRUNC);
    if (!file) {
        return false;
    }

    size_t written = file.write(buf, len);
    file.close();
    return written == len;
}

size_t InkplateBoard::sdReadFile(const char* path, uint8_t* buf, size_t maxLen) {
    if (!buf || maxLen == 0) return 0;

    SdFat& sd = _inkplate.getSdFat();
    FsFile file = sd.open(path, O_RDONLY);
    if (!file) return 0;

    // Leave room for a null terminator so text files can be read as C strings.
    size_t read = file.read(buf, maxLen - 1);
    file.close();

    if ((int)read <= 0) return 0;
    buf[read] = '\0';
    return read;
}
#endif
