// Native tests for the exponential back-off helper.
//
// computeBackoffSeconds() is pure — no hardware, no globals.
// Sequence: 120s (2min), ×3 each step, capped at 86400s (24h).

#include <unity.h>
#include "backoff.h"


void test_step_0_is_2_minutes(void) {
    TEST_ASSERT_EQUAL_UINT32(120, computeBackoffSeconds(0));
}

void test_each_step_triples_until_the_cap(void) {
    uint32_t expected = 120;
    for (int step = 1; step <= 5; ++step) {
        expected *= 3;
        TEST_ASSERT_EQUAL_UINT32(expected, computeBackoffSeconds(step));
    }
}

void test_step_6_hits_24h_cap(void) {
    // 120 * 3^6 = 120 * 729 = 87480 > 86400 cap.
    TEST_ASSERT_EQUAL_UINT32(86400, computeBackoffSeconds(6));
}

void test_well_above_cap_stays_at_cap(void) {
    TEST_ASSERT_EQUAL_UINT32(86400, computeBackoffSeconds(100));
}

void test_negative_step_returns_base(void) {
    TEST_ASSERT_EQUAL_UINT32(120, computeBackoffSeconds(-1));
    TEST_ASSERT_EQUAL_UINT32(120, computeBackoffSeconds(-100));
}


int main(int argc, char **argv) {
    (void)argc; (void)argv;
    UNITY_BEGIN();
    RUN_TEST(test_step_0_is_2_minutes);
    RUN_TEST(test_each_step_triples_until_the_cap);
    RUN_TEST(test_step_6_hits_24h_cap);
    RUN_TEST(test_well_above_cap_stays_at_cap);
    RUN_TEST(test_negative_step_returns_base);
    return UNITY_END();
}
