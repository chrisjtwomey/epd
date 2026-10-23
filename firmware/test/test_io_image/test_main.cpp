// Drawing a page, and the page cache on LittleFS.
#include <unity.h>

#include <string>

#include "MockBoard.h"
#include "epd.h"
#include "fake_globals.h"
#include "image.h"

static MockBoard board;

static const std::string kPage = "\x89PNG page one";
static const std::string kNewPage = "\x89PNG page two, longer";

static bool save(const std::string& page) {
    return savePageCache((const uint8_t*)page.data(), (int32_t)page.size());
}

void setUp() {
    board = MockBoard();
    epdBegin(board);
    LittleFS.reset();
}
void tearDown() {}

void test_a_page_is_drawn_inverted_from_memory() {
    TEST_ASSERT_EQUAL(ESP_OK, drawImage((const uint8_t*)kPage.data(), (int32_t)kPage.size()));
    TEST_ASSERT_EQUAL_STRING(kPage.c_str(), board.drawnPng.c_str());
    TEST_ASSERT_TRUE(board.drawnPngOptions == PngDraw::Invert);
}

void test_a_page_the_board_cannot_decode_is_a_draw_error() {
    board.drawPngReturn = false;
    TEST_ASSERT_EQUAL(ESP_ERR_EDRAW, drawImage((const uint8_t*)kPage.data(), (int32_t)kPage.size()));
}

void test_a_build_without_a_card_cannot_draw_from_a_path() {
    TEST_ASSERT_EQUAL(ESP_ERR_NOT_SUPPORTED, drawImage("/image.png"));
}

void test_the_cache_is_unavailable_when_littlefs_does_not_mount() {
    LittleFS.mountOk = false;
    TEST_ASSERT_FALSE(startPageCache());
}

void test_a_saved_page_is_drawn_from_the_cache() {
    TEST_ASSERT_TRUE(startPageCache());
    TEST_ASSERT_TRUE(save(kPage));
    TEST_ASSERT_TRUE(drawCachedPage());
    TEST_ASSERT_EQUAL_STRING(kPage.c_str(), board.drawnPng.c_str());
    TEST_ASSERT_FALSE(LittleFS.exists("/image.tmp"));
}

void test_a_new_page_replaces_the_cached_one() {
    TEST_ASSERT_TRUE(save(kPage));
    TEST_ASSERT_TRUE(save(kNewPage));
    TEST_ASSERT_TRUE(drawCachedPage());
    TEST_ASSERT_EQUAL_STRING(kNewPage.c_str(), board.drawnPng.c_str());
}

// The decoder draws a cut PNG as if it were whole, so a cut save must never
// become the cache.
void test_a_save_that_writes_short_keeps_the_last_good_page() {
    TEST_ASSERT_TRUE(save(kPage));
    LittleFS.writeLimit = 5;
    TEST_ASSERT_FALSE(save(kNewPage));
    TEST_ASSERT_FALSE(LittleFS.exists("/image.tmp"));
    TEST_ASSERT_TRUE(drawCachedPage());
    TEST_ASSERT_EQUAL_STRING(kPage.c_str(), board.drawnPng.c_str());
}

void test_a_save_that_cannot_replace_the_page_keeps_the_last_good_page() {
    TEST_ASSERT_TRUE(save(kPage));
    LittleFS.renameOk = false;
    TEST_ASSERT_FALSE(save(kNewPage));
    TEST_ASSERT_TRUE(drawCachedPage());
    TEST_ASSERT_EQUAL_STRING(kPage.c_str(), board.drawnPng.c_str());
}

void test_a_save_that_cannot_open_the_file_fails() {
    LittleFS.openOk = false;
    TEST_ASSERT_FALSE(save(kPage));
}

void test_without_a_cached_page_nothing_is_drawn() {
    TEST_ASSERT_FALSE(drawCachedPage());
    LittleFS.files["/image.png"] = "";
    TEST_ASSERT_FALSE(drawCachedPage());
    TEST_ASSERT_TRUE(board.drawnPng.empty());
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_a_page_is_drawn_inverted_from_memory);
    RUN_TEST(test_a_page_the_board_cannot_decode_is_a_draw_error);
    RUN_TEST(test_a_build_without_a_card_cannot_draw_from_a_path);
    RUN_TEST(test_the_cache_is_unavailable_when_littlefs_does_not_mount);
    RUN_TEST(test_a_saved_page_is_drawn_from_the_cache);
    RUN_TEST(test_a_new_page_replaces_the_cached_one);
    RUN_TEST(test_a_save_that_writes_short_keeps_the_last_good_page);
    RUN_TEST(test_a_save_that_cannot_replace_the_page_keeps_the_last_good_page);
    RUN_TEST(test_a_save_that_cannot_open_the_file_fails);
    RUN_TEST(test_without_a_cached_page_nothing_is_drawn);
    return UNITY_END();
}
