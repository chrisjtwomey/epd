// Native tests for formatLocalTime(): RFC 3339 local time in the zone TZ
// holds, as the server sends it.

#include <unity.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "local_time.h"

static const time_t kJanuary = 1768478400;   // 2026-01-15 12:00 UTC
static const time_t kJuly = 1784116800;      // 2026-07-15 12:00 UTC

static char out[LOCAL_TIME_MAX + 8];

static void useZone(const char* posixTz) {
    setenv("TZ", posixTz, 1);
    tzset();
}

void setUp(void) { memset(out, 'x', sizeof(out)); }

void tearDown(void) {
    unsetenv("TZ");
    tzset();
}

void test_no_zone_is_utc(void) {
    unsetenv("TZ");
    tzset();
    formatLocalTime(kJanuary, out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2026-01-15T12:00:00+00:00", out);
}

// Debian's form for Europe/Dublin: summer is the standard, winter a
// negative daylight shift.
void test_dublin_as_debian_writes_it(void) {
    useZone("IST-1GMT0,M10.5.0,M3.5.0/1");
    formatLocalTime(kJanuary, out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2026-01-15T12:00:00+00:00", out);
    formatLocalTime(kJuly, out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2026-07-15T13:00:00+01:00", out);
}

void test_dublin_as_macos_writes_it(void) {
    useZone("GMT0IST,M3.5.0/1,M10.5.0");
    formatLocalTime(kJanuary, out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2026-01-15T12:00:00+00:00", out);
    formatLocalTime(kJuly, out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2026-07-15T13:00:00+01:00", out);
}

void test_a_zone_west_of_utc(void) {
    useZone("EST5EDT,M3.2.0,M11.1.0");
    formatLocalTime(kJanuary, out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2026-01-15T07:00:00-05:00", out);
}

void test_a_half_hour_offset(void) {
    useZone("<+1030>-10:30<+11>-11,M10.1.0,M4.1.0");
    formatLocalTime(kJuly, out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2026-07-15T22:30:00+10:30", out);
}

void test_the_stamp_fills_its_buffer_exactly(void) {
    size_t n = formatLocalTime(kJanuary, out, LOCAL_TIME_MAX);
    TEST_ASSERT_EQUAL_UINT(LOCAL_TIME_MAX - 1, n);
    TEST_ASSERT_EQUAL_UINT(strlen(out), n);
}

void test_a_short_buffer_truncates_and_writes_nothing_past_it(void) {
    size_t n = formatLocalTime(kJanuary, out, 11);
    TEST_ASSERT_EQUAL_STRING("2026-01-15", out);
    TEST_ASSERT_EQUAL_UINT(10, n);
    TEST_ASSERT_EQUAL_CHAR('x', out[11]);
}

void test_nothing_is_written_without_a_buffer(void) {
    TEST_ASSERT_EQUAL_UINT(0, formatLocalTime(kJanuary, out, 0));
    TEST_ASSERT_EQUAL_CHAR('x', out[0]);
    TEST_ASSERT_EQUAL_UINT(0, formatLocalTime(kJanuary, nullptr, 16));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_no_zone_is_utc);
    RUN_TEST(test_dublin_as_debian_writes_it);
    RUN_TEST(test_dublin_as_macos_writes_it);
    RUN_TEST(test_a_zone_west_of_utc);
    RUN_TEST(test_a_half_hour_offset);
    RUN_TEST(test_the_stamp_fills_its_buffer_exactly);
    RUN_TEST(test_a_short_buffer_truncates_and_writes_nothing_past_it);
    RUN_TEST(test_nothing_is_written_without_a_buffer);
    return UNITY_END();
}
