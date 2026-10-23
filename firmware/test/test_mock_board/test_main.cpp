// Native host tests for sleep_utils using MockBoard.
//
// sleepFor() programs the RTC alarm relative to the current epoch, and
// sleepUntil() arms the board's wake source alongside it.
//
// Run with:  pio test -e native_mock

#include <unity.h>
#include "MockBoard.h"
#include "driver/rtc_io.h"
#include "epd.h"
#include "sleep_utils.h"

// The board the code under test draws on. epdBegin() hands it over the way a
// project's setup() does.
static MockBoard mockBoard;

void setUp(void) {
    mockBoard = MockBoard();
    epdBegin(mockBoard);
    g_timerWakeupUs = 0;
}

void tearDown(void) {}

// The wake pin is board-specific, so sleepUntil() must ask the board to arm its
// own wake source rather than enabling a hard-coded GPIO itself.
void test_sleep_for_sets_rtc_alarm_relative_to_epoch() {
    mockBoard.epochReturn = 1000;
    sleepFor(3600);
    TEST_ASSERT_TRUE(mockBoard.rtcSetAlarmEpochCalled);
    TEST_ASSERT_EQUAL(4600, mockBoard.lastAlarmEpoch);
    TEST_ASSERT_TRUE(mockBoard.enableWakeOnRtcAlarmCalled);
}

// The alarm must be programmed before the wake source is armed, otherwise the
// board could sleep on a stale alarm.
void test_sleep_sets_alarm_and_wake_source_together() {
    mockBoard.epochReturn = 200;
    sleepUntil(500);
    TEST_ASSERT_TRUE(mockBoard.rtcSetAlarmEpochCalled);
    TEST_ASSERT_TRUE(mockBoard.enableWakeOnRtcAlarmCalled);
    TEST_ASSERT_EQUAL(500, mockBoard.lastAlarmEpoch);
}

// A timer wake is a second wake source, not a replacement: a board whose RTC
// alarm never reaches the SoC still comes back.
void test_timer_wake_is_armed_alongside_the_rtc_alarm() {
    mockBoard.epochReturn = 1000;
    enableWakeOnTimer(15);
    sleepFor(10);
    TEST_ASSERT_EQUAL_UINT64(15000000ULL, g_timerWakeupUs);
    TEST_ASSERT_TRUE(mockBoard.enableWakeOnRtcAlarmCalled);
    TEST_ASSERT_EQUAL(1010, mockBoard.lastAlarmEpoch);
}

int main(int argc, char** argv) {
    (void)argc; (void)argv;
    UNITY_BEGIN();

    // sleepFor
    RUN_TEST(test_sleep_for_sets_rtc_alarm_relative_to_epoch);
    RUN_TEST(test_sleep_sets_alarm_and_wake_source_together);
    RUN_TEST(test_timer_wake_is_armed_alongside_the_rtc_alarm);

    return UNITY_END();
}
