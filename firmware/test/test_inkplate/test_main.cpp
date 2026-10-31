// The Inkplate board's pure parts. A page written a row at a time lands in
// the frame buffer exactly as the library's PNG path puts it there a pixel at
// a time, and PNGdec gives the rows the pixels the PNG holds. The RTC, kept in
// UTC, means the same moment whatever zone is set when it is read.
#include <unity.h>

#include <PNGdec.h>

#include <cstdint>
#include <cstring>
#include <ctime>
#include <vector>

#include "fixture.h"
#include "frame_rows.h"
#include "utc_scope.h"

// The library's own path, ported: pngle_on_draw's grey for an undithered
// pixel, and EPDDriver::writePixelInternal in 3-bit mode (InkplateLibrary
// 11.2.1).
#define RGB8BIT(r, g, b) ((54UL * (r) + 183UL * (g) + 19UL * (b)) >> 8)
#define RGB3BIT(r, g, b) ((RGB8BIT(r, g, b) * 7UL + 127UL) / 255UL)
static const uint8_t pixelMaskGLUT[2] = {0xF, 0xF0};

struct LibraryPanel {
    std::vector<uint8_t> memory;
    int16_t physicalWidth, physicalHeight;
    uint8_t rotation;
    int16_t width() const { return rotation & 1 ? physicalHeight : physicalWidth; }
    int16_t height() const { return rotation & 1 ? physicalWidth : physicalHeight; }

    void drawPixel(int16_t x, int16_t y, uint16_t color) {
        int16_t x0 = x, y0 = y;
        if (x0 > width() - 1 || y0 > height() - 1 || x0 < 0 || y0 < 0) return;
        int16_t t;
        switch (rotation) {
            case 1: t = x0; x0 = y0; y0 = t; x0 = height() - x0 - 1; break;
            case 2: x0 = width() - x0 - 1; y0 = height() - y0 - 1; break;
            case 3: t = x0; x0 = y0; y0 = t; y0 = width() - y0 - 1; break;
        }
        color &= 7;
        const int xb = x0 >> 1, xs = x0 & 1;
        uint8_t* p = memory.data() + (physicalWidth >> 1) * y0 + xb;
        *p = (pixelMaskGLUT[xs] & *p) | (xs ? color : color << 4);
    }
};

static uint32_t seed = 12345;
static uint8_t nextGrey() {
    seed = seed * 1103515245u + 12345u;
    return (uint8_t)(seed >> 16);
}

// Draw the same rows both ways onto a buffer already holding the same noise.
static void compare(int16_t w, int16_t h, uint8_t rotation, int x, int y, int rows, int cols) {
    const size_t bytes = (size_t)w * h / 2;
    std::vector<uint8_t> noise(bytes);
    for (auto& b : noise) b = nextGrey();

    LibraryPanel lib{noise, w, h, rotation};
    std::vector<uint8_t> ours = noise;
    FrameRows rowsWriter{ours.data(), w, h, rotation};

    std::vector<uint8_t> row(cols);
    for (int j = 0; j < rows; ++j) {
        for (auto& g : row) g = nextGrey();
        for (int i = 0; i < cols; ++i) lib.drawPixel(x + i, y + j, RGB3BIT(row[i], row[i], row[i]));
        rowsWriter.writeGreyRow(x, y + j, row.data(), cols);
    }
    TEST_ASSERT_EQUAL_UINT8_ARRAY(lib.memory.data(), ours.data(), bytes);
}

// The fixture's pixels, from two bits each.
static std::vector<uint8_t> fixturePixels() {
    std::vector<uint8_t> px(kFixtureWidth * kFixtureHeight);
    for (size_t i = 0; i < px.size(); ++i)
        px[i] = ((kFixturePixels[i / 4] >> (2 * (i % 4))) & 3) * 85;
    return px;
}

struct Decoded {
    std::vector<uint8_t> pixels;
    const FrameRows* rows;
    int x, y;
};

static int collectRow(PNGDRAW* draw) {
    auto* d = static_cast<Decoded*>(draw->pUser);
    memcpy(d->pixels.data() + draw->y * draw->iWidth, draw->pPixels, draw->iWidth);
    if (d->rows) d->rows->writeGreyRow(d->x, d->y + draw->y, draw->pPixels, draw->iWidth);
    return 1;
}

static PNG png;

static void decodeFixture(Decoded* into) {
    into->pixels.assign(kFixtureWidth * kFixtureHeight, 0);
    TEST_ASSERT_EQUAL(PNG_SUCCESS,
                      png.openRAM(const_cast<uint8_t*>(kFixturePng), sizeof(kFixturePng), collectRow));
    TEST_ASSERT_EQUAL(PNG_PIXEL_GRAYSCALE, png.getPixelType());
    TEST_ASSERT_EQUAL(8, png.getBpp());
    TEST_ASSERT_EQUAL(PNG_SUCCESS, png.decode(into, 0));
    png.close();
}

void setUp() {}
void tearDown() {}

// The same rows as compare(), written block by block.
static void compareBlocks(int16_t w, int16_t h, uint8_t rotation, int x, int y, int rows, int cols,
                          int block) {
    const size_t bytes = (size_t)w * h / 2;
    std::vector<uint8_t> noise(bytes);
    for (auto& b : noise) b = nextGrey();
    std::vector<uint8_t> grey((size_t)rows * cols);
    for (auto& g : grey) g = nextGrey();

    LibraryPanel lib{noise, w, h, rotation};
    for (int j = 0; j < rows; ++j)
        for (int i = 0; i < cols; ++i) {
            const uint8_t v = grey[(size_t)j * cols + i];
            lib.drawPixel(x + i, y + j, RGB3BIT(v, v, v));
        }

    std::vector<uint8_t> ours = noise;
    FrameRows writer{ours.data(), w, h, rotation};
    for (int j = 0; j < rows; j += block)
        writer.writeGreyRows(x, y + j, grey.data() + (size_t)j * cols, cols,
                             rows - j < block ? rows - j : block, cols);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(lib.memory.data(), ours.data(), bytes);
}

void test_every_grey_maps_as_the_library_maps_it() {
    for (int v = 0; v < 256; ++v)
        TEST_ASSERT_EQUAL_UINT8(RGB3BIT(v, v, v), grey3((uint8_t)v));
}

void test_a_whole_page_at_each_rotation() {
    // The Inkplate 10's panel, drawn full size at each rotation.
    for (uint8_t r = 0; r < 4; ++r) {
        const bool sideways = r & 1;
        compare(1200, 825, r, 0, 0, sideways ? 1200 : 825, sideways ? 825 : 1200);
    }
}

void test_an_odd_offset_and_pixels_off_the_panel() {
    for (uint8_t r = 0; r < 4; ++r) {
        compare(64, 40, r, 3, 5, 50, 70);      // runs off the right and the bottom
        compare(64, 40, r, -7, -3, 20, 30);    // starts off the left and the top
    }
}

void test_pngdec_gives_the_pixels_the_png_holds_through_every_row_filter() {
    Decoded d{{}, nullptr, 0, 0};
    decodeFixture(&d);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(fixturePixels().data(), d.pixels.data(), d.pixels.size());
}

void test_a_decoded_page_lands_where_the_library_draws_it() {
    const std::vector<uint8_t> px = fixturePixels();
    for (uint8_t r = 0; r < 4; ++r) {
        std::vector<uint8_t> noise(200 * 160 / 2);
        for (auto& b : noise) b = nextGrey();
        LibraryPanel lib{noise, 200, 160, r};
        for (int y = 0; y < kFixtureHeight; ++y)
            for (int x = 0; x < kFixtureWidth; ++x) {
                const uint8_t v = px[y * kFixtureWidth + x];
                lib.drawPixel(9 + x, 4 + y, RGB3BIT(v, v, v));
            }

        std::vector<uint8_t> ours = noise;
        FrameRows rows{ours.data(), 200, 160, r};
        Decoded d{{}, &rows, 9, 4};
        decodeFixture(&d);
        TEST_ASSERT_EQUAL_UINT8_ARRAY(lib.memory.data(), ours.data(), ours.size());
    }
}

void test_blocks_of_rows_land_as_rows_do() {
    for (uint8_t r = 0; r < 4; ++r) {
        const bool sideways = r & 1;
        compareBlocks(1200, 825, r, 0, 0, sideways ? 1200 : 825, sideways ? 825 : 1200, 16);
        compareBlocks(64, 40, r, 3, 5, 50, 70, 16);     // a last block of 2 rows, run off the panel
        compareBlocks(64, 40, r, -7, -3, 20, 30, 7);    // odd blocks, starting off the panel
        compareBlocks(64, 40, r, 2, 1, 33, 30, 1);      // a row at a time
    }
}

// What the library does to the RTC: an epoch to clock fields with
// localtime(), and back with mktime().
struct RtcFields {
    struct tm t;
    void set(time_t epoch) { t = *localtime(&epoch); }
    time_t get() const {
        struct tm copy = t;
        copy.tm_isdst = -1;
        return mktime(&copy);
    }
};

static const char* kDublin = "IST-1GMT0,M10.5.0,M3.5.0/1";

void test_the_rtc_means_the_same_moment_after_the_zone_is_lost() {
    // Written on a wake that knew the zone; read after a reset, which has none.
    const time_t summer = 1784000000;   // July 2026: Irish summer time
    setenv("TZ", kDublin, 1);
    tzset();
    RtcFields rtc;
    {
        UtcScope utc;
        rtc.set(summer);
    }
    unsetenv("TZ");
    tzset();
    UtcScope utc;
    TEST_ASSERT_EQUAL(summer, rtc.get());
}

void test_the_rtc_means_the_same_moment_across_a_change_of_the_clocks() {
    // Set before the clocks went back, read after: 25 October 2026.
    const time_t before = 1792890000;   // 23:00 GMT, 24 October: still summer time
    setenv("TZ", kDublin, 1);
    tzset();
    RtcFields rtc;
    {
        UtcScope utc;
        rtc.set(before);
    }
    UtcScope utc;
    TEST_ASSERT_EQUAL(before, rtc.get());
}

void test_the_zone_set_before_is_put_back() {
    setenv("TZ", kDublin, 1);
    tzset();
    { UtcScope utc; TEST_ASSERT_EQUAL_STRING("UTC0", getenv("TZ")); }
    TEST_ASSERT_EQUAL_STRING(kDublin, getenv("TZ"));

    unsetenv("TZ");
    { UtcScope utc; }
    TEST_ASSERT_NULL(getenv("TZ"));
}

void test_png_lines_fit_the_panels_with_their_alignment() {
    const int kDefault = (320 * 4 + 1) * 2;
    TEST_ASSERT_TRUE(pngLinesFit(1200, kDefault));   // Inkplate 10
    TEST_ASSERT_TRUE(pngLinesFit(1024, kDefault));   // Inkplate 6PLUS
    TEST_ASSERT_FALSE(pngLinesFit(1280, kDefault));  // Inkplate 5 V2: 30 bytes over
    TEST_ASSERT_TRUE(pngLinesFit(1280, 2592));
    TEST_ASSERT_FALSE(pngLinesFit(1280, 2591));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_every_grey_maps_as_the_library_maps_it);
    RUN_TEST(test_a_whole_page_at_each_rotation);
    RUN_TEST(test_an_odd_offset_and_pixels_off_the_panel);
    RUN_TEST(test_blocks_of_rows_land_as_rows_do);
    RUN_TEST(test_the_rtc_means_the_same_moment_after_the_zone_is_lost);
    RUN_TEST(test_the_rtc_means_the_same_moment_across_a_change_of_the_clocks);
    RUN_TEST(test_the_zone_set_before_is_put_back);
    RUN_TEST(test_pngdec_gives_the_pixels_the_png_holds_through_every_row_filter);
    RUN_TEST(test_a_decoded_page_lands_where_the_library_draws_it);
    RUN_TEST(test_png_lines_fit_the_panels_with_their_alignment);
    return UNITY_END();
}
