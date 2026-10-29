// Native tests for the battery voltage-to-capacity lookup.
//
// batteryPercent() is a pure function of the table — no hardware, no
// Arduino.h. Tests verify the two ends, the rows themselves, and the blend
// between rows.

#include <unity.h>
#include "battery.h"


void test_full_charge_voltage(void) {
    // 4.23 V is the first entry and should map to 100%.
    TEST_ASSERT_EQUAL_INT(100, batteryPercent(4.23));
}

void test_above_full_charge_voltage(void) {
    // Anything above the highest table entry should still return 100%.
    TEST_ASSERT_EQUAL_INT(100, batteryPercent(4.30));
    TEST_ASSERT_EQUAL_INT(100, batteryPercent(5.00));
}

void test_dead_voltage(void) {
    // 3.40 V is the last entry and should map to 0%.
    TEST_ASSERT_EQUAL_INT(0, batteryPercent(3.40));
}

void test_below_dead_voltage(void) {
    TEST_ASSERT_EQUAL_INT(0, batteryPercent(3.39));
    TEST_ASSERT_EQUAL_INT(0, batteryPercent(2.50));
    TEST_ASSERT_EQUAL_INT(0, batteryPercent(0.00));
}

void test_row_voltages_give_their_own_percent(void) {
    TEST_ASSERT_EQUAL_INT(50, batteryPercent(3.846));
    TEST_ASSERT_EQUAL_INT(30, batteryPercent(3.691));
    TEST_ASSERT_EQUAL_INT(10, batteryPercent(3.549));
    TEST_ASSERT_EQUAL_INT(5,  batteryPercent(3.514));
    TEST_ASSERT_EQUAL_INT(1,  batteryPercent(3.446));
}

void test_blends_between_rows(void) {
    // Between {3.495, 3} and {3.478, 2}: 0.24 of the way up rounds down,
    // 0.71 of the way up rounds up.
    TEST_ASSERT_EQUAL_INT(2, batteryPercent(3.482));
    TEST_ASSERT_EQUAL_INT(3, batteryPercent(3.490));
    // A quarter of the way up from {3.400, 0} to {3.446, 1} rounds down.
    TEST_ASSERT_EQUAL_INT(0, batteryPercent(3.4115));
}

void test_percent_never_rises_as_voltage_falls(void) {
    int last = batteryPercent(4.40);
    for (int mv = 4400; mv >= 3000; mv--) {
        int percent = batteryPercent(mv / 1000.0);
        TEST_ASSERT_TRUE_MESSAGE(percent <= last, "percent rose as voltage fell");
        TEST_ASSERT_TRUE(percent >= 0 && percent <= 100);
        last = percent;
    }
}


int main(int argc, char **argv) {
    (void)argc; (void)argv;
    UNITY_BEGIN();
    RUN_TEST(test_full_charge_voltage);
    RUN_TEST(test_above_full_charge_voltage);
    RUN_TEST(test_dead_voltage);
    RUN_TEST(test_below_dead_voltage);
    RUN_TEST(test_row_voltages_give_their_own_percent);
    RUN_TEST(test_blends_between_rows);
    RUN_TEST(test_percent_never_rises_as_voltage_falls);
    return UNITY_END();
}
