// The steps of one wake, against the fakes: the board, the link, the server.
#include <unity.h>

#include <stdlib.h>
#include <string>

#include <Preferences.h>
#include <sys/time.h>

#include "MockBoard.h"
#include "epd.h"
#include "epd_headers.h"
#include "fake_globals.h"
#include "io_test.h"
#include "settings.h"
#include "wake.h"

static MockBoard board;

static ClientConfig config(bool mqtt) {
    ClientConfig cfg = {};
    cfg.wifiSSID = "home";
    cfg.wifiPass = "secret";
    cfg.wifiConnectTimeoutSeconds = 3;
    cfg.mqttEnabled = mqtt;
    cfg.mqttBroker = "broker.local";
    cfg.mqttPort = 1883;
    cfg.mqttClientID = "io-test";
    cfg.mqttPrefix = "mqtt/epd";
    cfg.mqttRetries = 1;
    return cfg;
}

void setUp() {
    board = MockBoard();
    epdBegin(board);
    fake::http().reset();
    fake::lines().clear();
    fake::broker() = fake::Broker();
    fake::clockSetTo() = 0;
    Update = UpdateClass();
    Preferences().clear();
    WiFi.joinAfterMs = 0;
    g_wakeup_cause = ESP_SLEEP_WAKEUP_UNDEFINED;
}
void tearDown() {}

void test_start_takes_the_clock_from_the_rtc() {
    board.epochReturn = 1761134400;
    startBoard(1);
    TEST_ASSERT_EQUAL(1761134400, fake::clockSetTo());
}

void test_an_rtc_wake_clears_the_alarm() {
    g_wakeup_cause = ESP_SLEEP_WAKEUP_EXT0;
    logWakeReason();
    TEST_ASSERT_TRUE(board.rtcClearAlarmFlagCalled);
    TEST_ASSERT_TRUE(logged("woke by the RTC alarm"));
}

void test_any_other_wake_leaves_the_alarm() {
    const esp_sleep_wakeup_cause_t causes[] = {ESP_SLEEP_WAKEUP_EXT1, ESP_SLEEP_WAKEUP_TIMER,
                                               ESP_SLEEP_WAKEUP_TOUCHPAD, ESP_SLEEP_WAKEUP_ULP,
                                               ESP_SLEEP_WAKEUP_UNDEFINED};
    for (esp_sleep_wakeup_cause_t cause : causes) {
        g_wakeup_cause = cause;
        logWakeReason();
    }
    TEST_ASSERT_FALSE(board.rtcClearAlarmFlagCalled);
    TEST_ASSERT_TRUE(logged("woke by a reset or power-on"));
}

void test_the_battery_is_read_as_a_percentage() {
    board.batteryReturn = 4.25;
    TEST_ASSERT_EQUAL(100, readBatteryPercent());
    TEST_ASSERT_TRUE(logged("battery voltage: 4.25v"));
}

void test_the_server_sets_the_clock_the_rtc_and_the_zone() {
    ServerResponse rsp = {};
    rsp.serverEpoch = 1761134400;
    strcpy(rsp.serverTimezone, "GMT0IST,M3.5.0/1,M10.5.0");
    keepServerTime(rsp);
    TEST_ASSERT_EQUAL(1761134400, fake::clockSetTo());
    TEST_ASSERT_EQUAL(1761134400, board.lastSetEpoch);
    TEST_ASSERT_EQUAL_STRING("GMT0IST,M3.5.0/1,M10.5.0", getenv("TZ"));
}

void test_a_server_without_a_clock_leaves_the_rtc() {
    ServerResponse rsp = {};
    keepServerTime(rsp);
    TEST_ASSERT_EQUAL(0, fake::clockSetTo());
    TEST_ASSERT_FALSE(board.rtcSetEpochCalled);
}

void test_no_wifi_ends_the_wake_early() {
    WiFi.joinAfterMs = -1;
    TEST_ASSERT_EQUAL(ESP_ERR_TIMEOUT, connectNetwork(config(true)));
    TEST_ASSERT_EQUAL(0, fake::broker().connects);
}

void test_the_network_logs_to_the_broker_under_the_boards_topic() {
    TEST_ASSERT_EQUAL(ESP_OK, connectNetwork(config(true)));
    TEST_ASSERT_EQUAL_STRING("broker.local", fake::broker().server.c_str());
    TEST_ASSERT_EQUAL_STRING("mqtt/epd/io-test", fake::lines().topic.c_str());
}

void test_a_broker_that_does_not_answer_still_lets_the_wake_go_on() {
    fake::broker().up = false;
    TEST_ASSERT_EQUAL(ESP_OK, connectNetwork(config(true)));
    TEST_ASSERT_TRUE(logged("failed to connect remote logging"));
}

void test_a_page_is_fetched_on_a_later_try_and_sets_the_clock() {
    answer(500);
    answer(200, "PNG").headers = {{EPD_H_SERVER_EPOCH, "1761134400"}};
    PageFetch page = {};
    page.length = 1000;
    const char* err = nullptr;
    TEST_ASSERT_TRUE(fetchPage("http://server/today.png", "ua", 1, &page, &err));
    TEST_ASSERT_EQUAL(3, page.length);
    TEST_ASSERT_EQUAL(1761134400, fake::clockSetTo());
    TEST_ASSERT_EQUAL(2, (int)fake::http().requests.size());
    free(page.data);
}

void test_a_page_that_never_arrives_says_so() {
    answer(500);
    answer(500);
    PageFetch page = {};
    page.length = 1000;
    const char* err = nullptr;
    TEST_ASSERT_FALSE(fetchPage("http://server/today.png", "ua", 1, &page, &err));
    TEST_ASSERT_EQUAL_STRING("file download error", err);
}

void test_a_drawn_page_gets_its_overlay_then_one_refresh() {
    std::string page = "PNG";
    PageFetch fetched = {(uint8_t*)&page[0], 3, {}};
    int overlays = 0;
    const char* err = nullptr;
    TEST_ASSERT_TRUE(drawPage(fetched, nullptr, 2, [&] { ++overlays; }, &err));
    TEST_ASSERT_EQUAL(1, overlays);
    TEST_ASSERT_EQUAL(1, board.displayCount);
}

void test_a_page_that_will_not_draw_is_tried_then_reported() {
    board.drawPngReturn = false;
    std::string page = "PNG";
    PageFetch fetched = {(uint8_t*)&page[0], 3, {}};
    const char* err = nullptr;
    TEST_ASSERT_FALSE(drawPage(fetched, nullptr, 2, nullptr, &err));
    TEST_ASSERT_EQUAL(3, board.clearDisplayCount);
    TEST_ASSERT_EQUAL(0, board.displayCount);
    TEST_ASSERT_EQUAL_STRING("image load error", err);
}

static ServerResponse offer(const char* version) {
    ServerResponse rsp = {};
    strcpy(rsp.firmwareVersion, version);
    strcpy(rsp.firmwareURL, "http://server/firmware.bin");
    return rsp;
}

void test_no_offer_asks_for_nothing() {
    takeOfferedUpdate(ServerResponse{}, "ua", 100, 30);
    TEST_ASSERT_TRUE(fake::http().requests.empty());
}

void test_an_image_this_board_rolled_back_from_is_not_taken_again() {
    Preferences prefs;
    prefs.putString("ota_rejected", "v1.3.0");
    takeOfferedUpdate(offer("v1.3.0"), "ua", 100, 30);
    TEST_ASSERT_TRUE(fake::http().requests.empty());
    TEST_ASSERT_TRUE(logged("this board rolled back from it"));
}

void test_an_update_waits_for_the_battery() {
    takeOfferedUpdate(offer("v1.3.0"), "ua", 20, 30);
    TEST_ASSERT_TRUE(fake::http().requests.empty());
    TEST_ASSERT_TRUE(logged("battery is 20%; waiting"));
}

void test_an_offered_update_is_asked_for() {
    answer(304);
    takeOfferedUpdate(offer("v1.3.0"), "ua", 100, 30);
    TEST_ASSERT_EQUAL_STRING("http://server/firmware.bin", lastRequest().url.c_str());
    TEST_ASSERT_EQUAL_STRING("v1.2.0", lastRequest().header("x-ESP32-version").c_str());
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_start_takes_the_clock_from_the_rtc);
    RUN_TEST(test_an_rtc_wake_clears_the_alarm);
    RUN_TEST(test_any_other_wake_leaves_the_alarm);
    RUN_TEST(test_the_battery_is_read_as_a_percentage);
    RUN_TEST(test_the_server_sets_the_clock_the_rtc_and_the_zone);
    RUN_TEST(test_a_server_without_a_clock_leaves_the_rtc);
    RUN_TEST(test_no_wifi_ends_the_wake_early);
    RUN_TEST(test_the_network_logs_to_the_broker_under_the_boards_topic);
    RUN_TEST(test_a_broker_that_does_not_answer_still_lets_the_wake_go_on);
    RUN_TEST(test_a_page_is_fetched_on_a_later_try_and_sets_the_clock);
    RUN_TEST(test_a_page_that_never_arrives_says_so);
    RUN_TEST(test_a_drawn_page_gets_its_overlay_then_one_refresh);
    RUN_TEST(test_a_page_that_will_not_draw_is_tried_then_reported);
    RUN_TEST(test_no_offer_asks_for_nothing);
    RUN_TEST(test_an_image_this_board_rolled_back_from_is_not_taken_again);
    RUN_TEST(test_an_update_waits_for_the_battery);
    RUN_TEST(test_an_offered_update_is_asked_for);
    return UNITY_END();
}
