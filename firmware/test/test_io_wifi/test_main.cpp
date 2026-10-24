// Joining Wi-Fi, and keeping a board that stays awake on it. The join keeps
// what it was given, so the test that runs before any join comes first.
#include <unity.h>

#include "fake_globals.h"
#include "io_test.h"
#include "network_utils.h"

static bool dropDuringWait = false;
static void dropOnce(TickType_t) {
    if (!dropDuringWait) return;
    dropDuringWait = false;
    WiFi.drop(2);
}

void setUp() {
    fake::lines().clear();
    fake::onSemaphoreWait() = dropOnce;
    WiFi.joinAfterMs = 250;
    WiFi.beginCount = 0;
    WiFi.onHintedChannel = true;
}
void tearDown() {}

void test_before_any_join_there_is_nothing_to_keep() {
    keepWiFiConnected();
    TEST_ASSERT_EQUAL(0, WiFi.beginCount);
}

void test_a_join_ends_once_the_board_has_an_address() {
    const uint32_t start = millis();
    TEST_ASSERT_EQUAL(ESP_OK, configureWiFi("home", "secret", 10));
    TEST_ASSERT_EQUAL(WIFI_STA, WiFi.mode_);
    TEST_ASSERT_EQUAL(1, WiFi.beginCount);
    TEST_ASSERT_TRUE(millis() - start < 1000);
    TEST_ASSERT_TRUE(logged("wifi connected in"));
}

void test_a_join_that_times_out_says_why_it_last_failed() {
    WiFi.joinAfterMs = -1;
    dropDuringWait = true;
    const uint32_t start = millis();
    // Another network, so no channel kept from the join before applies.
    TEST_ASSERT_EQUAL(ESP_ERR_TIMEOUT, configureWiFi("work", "wrong", 3));
    TEST_ASSERT_EQUAL(3000u, millis() - start);
    TEST_ASSERT_TRUE(logged("wifi not joined in 3000 ms; last reason 2 (AUTH_EXPIRE)"));
}

void test_a_timeout_below_one_second_waits_one_second() {
    WiFi.joinAfterMs = -1;
    const uint32_t start = millis();
    TEST_ASSERT_EQUAL(ESP_ERR_TIMEOUT, configureWiFi("home", "wrong", 0));
    TEST_ASSERT_EQUAL(1000u, millis() - start);
}

void test_the_next_join_goes_straight_to_the_channel_last_joined() {
    TEST_ASSERT_EQUAL(ESP_OK, configureWiFi("home", "secret", 10));
    TEST_ASSERT_EQUAL(ESP_OK, configureWiFi("home", "secret", 10));
    TEST_ASSERT_EQUAL(6, WiFi.lastBeginChannel);
    TEST_ASSERT_TRUE(logged("connecting to WiFi SSID home on channel 6"));
}

void test_a_kept_channel_that_fails_falls_back_to_a_scan() {
    TEST_ASSERT_EQUAL(ESP_OK, configureWiFi("home", "secret", 10));
    WiFi.beginCount = 0;
    WiFi.onHintedChannel = false;
    const uint32_t start = millis();
    TEST_ASSERT_EQUAL(ESP_OK, configureWiFi("home", "secret", 10));
    TEST_ASSERT_EQUAL(2, WiFi.beginCount);
    TEST_ASSERT_EQUAL(0, WiFi.lastBeginChannel);
    TEST_ASSERT_TRUE(millis() - start >= 3000);
    TEST_ASSERT_TRUE(logged("wifi not joined on channel 6; scanning for home"));
}

void test_a_dropped_link_is_joined_again_every_30_s() {
    TEST_ASSERT_EQUAL(ESP_OK, configureWiFi("home", "secret", 10));
    WiFi.beginCount = 0;
    WiFi.joinAfterMs = -1;
    WiFi.drop(201);

    keepWiFiConnected();  // the framework's own reconnect has the first 30 s
    delay(29000);
    keepWiFiConnected();
    TEST_ASSERT_EQUAL(0, WiFi.beginCount);
    delay(1000);
    keepWiFiConnected();
    TEST_ASSERT_EQUAL(1, WiFi.beginCount);
    TEST_ASSERT_TRUE(logged("wifi down for 30 s; connecting again"));

    WiFi.status_ = WL_CONNECTED;
    delay(5000);
    keepWiFiConnected();
    TEST_ASSERT_TRUE(logged("wifi back after 35 s"));
    TEST_ASSERT_TRUE(logged("lost with reason 201 (NO_AP_FOUND)"));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_before_any_join_there_is_nothing_to_keep);
    RUN_TEST(test_a_join_ends_once_the_board_has_an_address);
    RUN_TEST(test_a_join_that_times_out_says_why_it_last_failed);
    RUN_TEST(test_a_timeout_below_one_second_waits_one_second);
    RUN_TEST(test_the_next_join_goes_straight_to_the_channel_last_joined);
    RUN_TEST(test_a_kept_channel_that_fails_falls_back_to_a_scan);
    RUN_TEST(test_a_dropped_link_is_joined_again_every_30_s);
    return UNITY_END();
}
