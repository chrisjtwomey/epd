// When a board that stays awake starts a new Wi-Fi connection attempt.
#include <unity.h>
#include <cstdint>

#include "wifi_retry.h"

void setUp() {}
void tearDown() {}

void test_nothing_is_due_while_connected() {
    WifiRetry r(30000);
    TEST_ASSERT_FALSE(r.due(0, true));
    TEST_ASSERT_FALSE(r.due(600000, true));
    TEST_ASSERT_FALSE(r.down());
}

void test_the_first_attempt_is_one_interval_after_the_loss() {
    WifiRetry r(30000);
    TEST_ASSERT_FALSE_MESSAGE(r.due(1000, false), "the framework gets the first try");
    TEST_ASSERT_TRUE(r.down());
    TEST_ASSERT_FALSE(r.due(30999, false));
    TEST_ASSERT_TRUE(r.due(31000, false));
}

void test_attempts_repeat_every_interval_while_down() {
    WifiRetry r(30000);
    r.due(0, false);
    TEST_ASSERT_TRUE(r.due(30000, false));
    TEST_ASSERT_FALSE(r.due(59999, false));
    TEST_ASSERT_TRUE(r.due(60000, false));
    TEST_ASSERT_EQUAL_UINT32(60000, r.downForMs(60000));
}

void test_a_new_loss_counts_from_its_own_start() {
    WifiRetry r(30000);
    r.due(0, false);
    r.due(30000, false);
    TEST_ASSERT_FALSE(r.due(40000, true));
    TEST_ASSERT_EQUAL_UINT32(0, r.downForMs(40000));
    TEST_ASSERT_FALSE(r.due(50000, false));
    TEST_ASSERT_FALSE(r.due(79999, false));
    TEST_ASSERT_TRUE(r.due(80000, false));
}

void test_the_retry_holds_across_the_uptime_wrapping() {
    WifiRetry r(30000);
    r.due(0xFFFFF000u, false);
    TEST_ASSERT_FALSE(r.due(0xFFFFF000u + 29999, false));
    TEST_ASSERT_TRUE(r.due(0xFFFFF000u + 30000, false));   // wrapped past zero
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_nothing_is_due_while_connected);
    RUN_TEST(test_the_first_attempt_is_one_interval_after_the_loss);
    RUN_TEST(test_attempts_repeat_every_interval_while_down);
    RUN_TEST(test_a_new_loss_counts_from_its_own_start);
    RUN_TEST(test_the_retry_holds_across_the_uptime_wrapping);
    UNITY_END();
    return 0;
}
