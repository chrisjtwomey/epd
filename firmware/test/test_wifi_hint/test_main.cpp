// The access point a board last joined, kept for the next wake.
#include <unity.h>
#include <cstdint>

#include "wifi_hint.h"

static const uint8_t kBssid[6] = {0x10, 0x7b, 0x44, 0x01, 0x02, 0x03};

void setUp() {}
void tearDown() {}

void test_a_board_that_never_joined_has_no_hint() {
    WifiHint h = {};
    TEST_ASSERT_FALSE(h.usableFor("home"));
}

void test_the_hint_is_for_the_network_it_was_kept_for() {
    WifiHint h = {};
    h.keep("home", 6, kBssid);
    TEST_ASSERT_TRUE(h.usableFor("home"));
    TEST_ASSERT_FALSE(h.usableFor("home-5g"));
    TEST_ASSERT_EQUAL_UINT8(6, h.channel);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(kBssid, h.bssid, 6);
}

void test_a_forgotten_hint_is_not_used() {
    WifiHint h = {};
    h.keep("home", 6, kBssid);
    h.forget();
    TEST_ASSERT_FALSE(h.usableFor("home"));
}

void test_a_join_without_a_channel_or_access_point_leaves_no_hint() {
    WifiHint h = {};
    h.keep("home", 6, kBssid);
    h.keep("home", 0, kBssid);
    TEST_ASSERT_FALSE(h.usableFor("home"));
    h.keep("home", 6, nullptr);
    TEST_ASSERT_FALSE(h.usableFor("home"));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_a_board_that_never_joined_has_no_hint);
    RUN_TEST(test_the_hint_is_for_the_network_it_was_kept_for);
    RUN_TEST(test_a_forgotten_hint_is_not_used);
    RUN_TEST(test_a_join_without_a_channel_or_access_point_leaves_no_hint);
    return UNITY_END();
}
