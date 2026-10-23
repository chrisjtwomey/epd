// Downloads and posts from a board without a key, and the pairing that
// gives it one. The board reads its key once, so the tests that pair come
// last.
#include <unity.h>

#include <stdlib.h>
#include <string>

#include <Preferences.h>
#include <mbedtls/base64.h>

#include "board_key.h"
#include "epd_headers.h"
#include "fake_globals.h"
#include "io_test.h"
#include "network_utils.h"
#include "settings_store.h"

static const char kPageURL[] = "http://server:8080/today.png";
static const char kPostURL[] = "http://server:8080/sensor-readings";

void setUp() {
    fake::http().reset();
    fake::lines().clear();
    fake::tasksCanStart() = true;
    WiFi.setSleep(true);
}
void tearDown() {}

static uint8_t* download(int32_t* size, ServerResponse* rsp = nullptr) {
    return downloadFile(kPageURL, "my-display/v1.2.0", size, rsp);
}

void test_a_page_arrives_with_what_the_server_said() {
    answer(200, "PNG-BYTES").headers = {
        {EPD_H_NEXT_REFRESH, "3600"},
        {EPD_H_NEXT_URL, "http://server:8080/hourly.png"},
        {EPD_H_SERVER_VERSION, "v0.13.0"},
        {EPD_H_SERVER_EPOCH, "1761134400"},
        {EPD_H_SERVER_TIMEZONE, "GMT0"},
        {EPD_H_FIRMWARE_VERSION, "v1.3.0"},
        {EPD_H_FIRMWARE_URL, "http://server:8080/firmware.bin"},
        {EPD_H_NEXT_SENSOR_POLL, "300"},
    };
    ServerResponse rsp = {};
    int32_t size = 100;
    uint8_t* page = download(&size, &rsp);
    TEST_ASSERT_NOT_NULL(page);
    TEST_ASSERT_EQUAL(9, size);
    TEST_ASSERT_EQUAL_MEMORY("PNG-BYTES", page, 9);
    TEST_ASSERT_EQUAL(3600, rsp.nextRefreshSeconds);
    TEST_ASSERT_EQUAL_STRING("http://server:8080/hourly.png", rsp.nextURL);
    TEST_ASSERT_EQUAL_STRING("v0.13.0", rsp.serverVersion);
    TEST_ASSERT_EQUAL(1761134400, rsp.serverEpoch);
    TEST_ASSERT_EQUAL_STRING("GMT0", rsp.serverTimezone);
    TEST_ASSERT_EQUAL_STRING("v1.3.0", rsp.firmwareVersion);
    TEST_ASSERT_EQUAL_STRING("http://server:8080/firmware.bin", rsp.firmwareURL);
    TEST_ASSERT_EQUAL(300, rsp.nextSensorPollSeconds);
    TEST_ASSERT_TRUE(logged("reached the server at"));
    free(page);
}

void test_a_request_names_the_board_and_keeps_its_wifi_sleep() {
    answer(200, "x");
    int32_t size = 10;
    free(download(&size));
    TEST_ASSERT_EQUAL_STRING("my-display/v1.2.0", lastRequest().userAgent.c_str());
    TEST_ASSERT_EQUAL_STRING("io-test", lastRequest().header(EPD_H_DEVICE).c_str());
    TEST_ASSERT_EQUAL_STRING("v1.2.0", lastRequest().header(EPD_H_DEVICE_VERSION).c_str());
    TEST_ASSERT_TRUE(lastRequest().header(EPD_H_KEY_ID).empty());
    TEST_ASSERT_TRUE(WiFi.getSleep());
}

void test_a_header_too_long_or_malformed_is_ignored() {
    answer(200, "x").headers = {{EPD_H_NEXT_URL, std::string(300, 'u')},
                                {EPD_H_NEXT_REFRESH, "soon"}};
    ServerResponse rsp = {};
    rsp.nextRefreshSeconds = 60;
    int32_t size = 10;
    free(download(&size, &rsp));
    TEST_ASSERT_EQUAL_STRING("", rsp.nextURL);
    TEST_ASSERT_EQUAL(60, rsp.nextRefreshSeconds);
    TEST_ASSERT_TRUE(logged("value is longer than 255 characters"));
    TEST_ASSERT_TRUE(logged("value 'soon' is malformed"));
}

void test_a_chunked_page_arrives_whole() {
    fake::HttpAnswer& a = answer(200, "4\r\nPNG-\r\n5\r\nBYTES\r\n0\r\n\r\n");
    a.contentLength = false;
    a.headers = {{"Transfer-Encoding", "chunked"}};
    int32_t size = 100;
    uint8_t* page = download(&size);
    TEST_ASSERT_NOT_NULL(page);
    TEST_ASSERT_EQUAL(9, size);
    TEST_ASSERT_EQUAL_MEMORY("PNG-BYTES", page, 9);
    free(page);
}

void test_no_page_comes_back_from_an_error_or_a_lost_server() {
    int32_t size = 10;
    answer(404);
    TEST_ASSERT_NULL(download(&size));
    TEST_ASSERT_TRUE(logged("answered 404"));
    TEST_ASSERT_NULL(download(&size));  // nothing queued: the connection is refused
    TEST_ASSERT_TRUE(logged("failed: error -1"));
}

void test_an_empty_page_is_refused() {
    int32_t size = 10;
    answer(200, "");
    TEST_ASSERT_NULL(download(&size));
    fake::HttpAnswer& chunked = answer(200, "0\r\n\r\n");
    chunked.contentLength = false;
    chunked.headers = {{"Transfer-Encoding", "chunked"}};
    TEST_ASSERT_NULL(download(&size));
    TEST_ASSERT_TRUE(logged("empty answer from"));
}

void test_a_page_larger_than_allowed_is_refused_before_it_is_read() {
    answer(200, "0123456789ABC");
    int32_t size = 10;
    TEST_ASSERT_NULL(download(&size));
    TEST_ASSERT_TRUE(logged("is 13 bytes, more than the 10 allowed"));
}

void test_a_page_that_stops_arriving_is_refused() {
    answer(200, "PNG-BYTES").stallAt = 4;
    int32_t size = 100;
    TEST_ASSERT_NULL(download(&size));
    TEST_ASSERT_TRUE(logged("failed after 4 bytes"));
}

void test_a_post_returns_the_servers_code_and_headers() {
    answer(204).headers = {{EPD_H_SERVER_EPOCH, "1761134400"}};
    ServerResponse rsp = {};
    TEST_ASSERT_EQUAL(204, postJson(kPostURL, "ua", "{\"ts\":1}", &rsp));
    TEST_ASSERT_EQUAL(1761134400, rsp.serverEpoch);
    TEST_ASSERT_EQUAL_STRING("POST", lastRequest().method.c_str());
    TEST_ASSERT_EQUAL_STRING("{\"ts\":1}", lastRequest().body.c_str());
    TEST_ASSERT_EQUAL_STRING("application/json", lastRequest().header("Content-Type").c_str());
    TEST_ASSERT_TRUE(lastRequest().header("Signature").empty());
}

void test_a_post_with_nowhere_to_keep_the_answer_still_posts() {
    answer(200);
    TEST_ASSERT_EQUAL(200, postJson(kPostURL, "ua", "{}", nullptr));
}

void test_a_post_the_server_never_sees_says_why() {
    TEST_ASSERT_EQUAL(HTTPC_ERROR_CONNECTION_REFUSED, postJson(kPostURL, "ua", "{}", nullptr));
    TEST_ASSERT_TRUE(logged("POST http://server:8080/sensor-readings failed"));
}

// The server's half of the key: 0x04, then x and y. The fake ECDH takes x as
// the shared secret (test/fakes/mbedtls/ecp.h).
static std::string serverHalf(uint8_t xByte) {
    uint8_t point[65];
    point[0] = 0x04;
    memset(point + 1, xByte, 32);
    memset(point + 33, 0x22, 32);
    unsigned char b64[96];
    size_t len = 0;
    mbedtls_base64_encode(b64, sizeof(b64), &len, point, sizeof(point));
    return "{\"key\":\"" + std::string((const char*)b64, len) + "\"}";
}

static BoardKey keyFrom(uint8_t xByte) {
    uint8_t shared[32], key[BOARD_KEY_LEN];
    memset(shared, xByte, sizeof(shared));
    deriveBoardKey(shared, sizeof(shared), "io-test", key);
    return boardKeyFrom(key);
}

static void askToPair() { answer(401).headers = {{EPD_H_KEY, "pair"}}; }

void test_a_pair_that_cannot_start_its_task_keeps_the_board_unpaired() {
    askToPair();
    fake::tasksCanStart() = false;
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", "{}", nullptr));
    TEST_ASSERT_TRUE(logged("no memory for its task"));
    TEST_ASSERT_FALSE(loadBoardKey().present);
}

void test_a_pair_the_server_refuses_keeps_the_board_unpaired() {
    askToPair();
    answer(500);
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", "{}", nullptr));
    TEST_ASSERT_TRUE(logged("pairing with http://server:8080/pair failed: 500"));
    TEST_ASSERT_FALSE(loadBoardKey().present);
}

void test_a_server_half_that_is_not_a_key_keeps_the_board_unpaired() {
    askToPair();
    answer(200, serverHalf(0x00));  // x of zero stands for a point off the curve
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", "{}", nullptr));
    TEST_ASSERT_TRUE(logged("the server's half of the key cannot be read"));
    askToPair();
    answer(200, "{\"key\":\"QUJD\"}");
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", "{}", nullptr));
    TEST_ASSERT_FALSE(loadBoardKey().present);
}

// Last: from here on the board holds a key.
void test_an_unpaired_board_pairs_when_asked_and_posts_again_signed() {
    askToPair();
    answer(200, serverHalf(0x11));
    answer(401).headers = {{EPD_H_KEY, "pending"}};
    TEST_ASSERT_EQUAL(401, postJson(kPostURL, "ua", "{\"ts\":1}", nullptr));

    const BoardKey expected = keyFrom(0x11);
    TEST_ASSERT_TRUE(loadBoardKey().present);
    TEST_ASSERT_EQUAL_STRING(expected.id, loadBoardKey().id);
    TEST_ASSERT_EQUAL(3, (int)fake::http().requests.size());
    const fake::HttpRequest& pair = fake::http().requests[1];
    TEST_ASSERT_EQUAL_STRING("http://server:8080/pair", pair.url.c_str());
    TEST_ASSERT_TRUE(pair.body.find("\"device\":\"io-test\"") != std::string::npos);
    TEST_ASSERT_FALSE(lastRequest().header("Signature").empty());
    TEST_ASSERT_TRUE(logged("waits for approval in the server's Settings"));
}

int main() {
    Preferences().clear();
    UNITY_BEGIN();
    RUN_TEST(test_a_page_arrives_with_what_the_server_said);
    RUN_TEST(test_a_request_names_the_board_and_keeps_its_wifi_sleep);
    RUN_TEST(test_a_header_too_long_or_malformed_is_ignored);
    RUN_TEST(test_a_chunked_page_arrives_whole);
    RUN_TEST(test_no_page_comes_back_from_an_error_or_a_lost_server);
    RUN_TEST(test_an_empty_page_is_refused);
    RUN_TEST(test_a_page_larger_than_allowed_is_refused_before_it_is_read);
    RUN_TEST(test_a_page_that_stops_arriving_is_refused);
    RUN_TEST(test_a_post_returns_the_servers_code_and_headers);
    RUN_TEST(test_a_post_with_nowhere_to_keep_the_answer_still_posts);
    RUN_TEST(test_a_post_the_server_never_sees_says_why);
    RUN_TEST(test_a_pair_that_cannot_start_its_task_keeps_the_board_unpaired);
    RUN_TEST(test_a_pair_the_server_refuses_keeps_the_board_unpaired);
    RUN_TEST(test_a_server_half_that_is_not_a_key_keeps_the_board_unpaired);
    RUN_TEST(test_an_unpaired_board_pairs_when_asked_and_posts_again_signed);
    return UNITY_END();
}
