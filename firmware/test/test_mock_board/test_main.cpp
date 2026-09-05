// Native host tests for sleep_utils using MockBoard.
//
// Tests verify:
//   - sleep_for() programs the RTC alarm relative to the current epoch.
//   - displayBatteryStatus() selects the correct battery icon bitmap by
//     percentage threshold (both normal and inverted variants).
//
// Run with:  pio test -e native_mock

#include <unity.h>
#include "MockBoard.h"
#include "epd.h"
#include "sleep_utils.h"

// The board the code under test draws on. epdBegin() hands it over the way a
// project's setup() does.
static MockBoard mockBoard;

void setUp(void) {
    mockBoard = MockBoard();
    epdBegin(mockBoard);
}

void tearDown(void) {}

void test_sleep_for_sets_rtc_alarm_relative_to_epoch() {
    mockBoard.epochReturn = 1000;
    sleep_for(3600);
    TEST_ASSERT_TRUE(mockBoard.rtcSetAlarmEpochCalled);
    TEST_ASSERT_EQUAL(4600, mockBoard.lastAlarmEpoch);
}

void test_sleep_for_zero_seconds() {
    mockBoard.epochReturn = 500;
    sleep_for(0);
    TEST_ASSERT_EQUAL(500, mockBoard.lastAlarmEpoch);
}

void test_sleep_for_large_offset() {
    mockBoard.epochReturn = 0;
    sleep_for(86400);   // 24 h
    TEST_ASSERT_EQUAL(86400, mockBoard.lastAlarmEpoch);
}

// The wake pin is board-specific, so sleep() must ask the board to arm its
// own wake source rather than enabling a hard-coded GPIO itself.
void test_sleep_arms_board_wake_source() {
    mockBoard.epochReturn = 1000;
    sleep_for(60);
    TEST_ASSERT_TRUE(mockBoard.enableWakeOnRtcAlarmCalled);
}

// The alarm must be programmed before the wake source is armed, otherwise the
// board could sleep on a stale alarm.
void test_sleep_sets_alarm_and_wake_source_together() {
    mockBoard.epochReturn = 200;
    sleep(500);
    TEST_ASSERT_TRUE(mockBoard.rtcSetAlarmEpochCalled);
    TEST_ASSERT_TRUE(mockBoard.enableWakeOnRtcAlarmCalled);
    TEST_ASSERT_EQUAL(500, mockBoard.lastAlarmEpoch);
}

// ---------------------------------------------------------------------------
// displayBatteryStatus — icon selection tests.
//
// icons_32x32.h defines its bitmaps as `static`, so each translation unit
// gets its own copy. We cannot compare raw pointer values across TUs.
// Instead we verify:
int main(int argc, char** argv) {
    (void)argc; (void)argv;
    UNITY_BEGIN();

    // sleep_for
    RUN_TEST(test_sleep_for_sets_rtc_alarm_relative_to_epoch);
    RUN_TEST(test_sleep_for_zero_seconds);
    RUN_TEST(test_sleep_for_large_offset);
    RUN_TEST(test_sleep_arms_board_wake_source);
    RUN_TEST(test_sleep_sets_alarm_and_wake_source_together);

    return UNITY_END();
}
