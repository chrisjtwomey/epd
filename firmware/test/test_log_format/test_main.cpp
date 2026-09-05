// Native tests for the line the client's logf() writes.
//
// The old logf() sized its buffer with snprintf(NULL, 0, fmt, args), which
// passes the va_list itself as one argument. A format with several %s then
// read past the arguments and the board panicked in strlen.

#include <unity.h>
#include <string.h>
#include "log_format.h"

static char out[64];

// A variadic wrapper, because a test cannot build a va_list by hand.
static size_t format(size_t size, const char* prefix, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    size_t n = formatLog(out, size, prefix, fmt, args);
    va_end(args);
    return n;
}

void setUp(void) { memset(out, 'x', sizeof(out)); }
void tearDown(void) {}

void test_the_prefix_comes_first(void) {
    size_t n = format(sizeof(out), "INFO - ", "hello");
    TEST_ASSERT_EQUAL_STRING("INFO - hello", out);
    TEST_ASSERT_EQUAL_UINT(strlen(out), n);
}

void test_three_strings_in_one_line(void) {
    format(sizeof(out), "", "%s -> %s from %s", "v1.5.1", "v1.6.0", "http://h/f");
    TEST_ASSERT_EQUAL_STRING("v1.5.1 -> v1.6.0 from http://h/f", out);
}

void test_mixed_conversions(void) {
    format(sizeof(out), "", "%s %d%% (%d/%d)", "update", 40, 4, 10);
    TEST_ASSERT_EQUAL_STRING("update 40% (4/10)", out);
}

void test_no_arguments_at_all(void) {
    format(sizeof(out), "WARN - ", "no card");
    TEST_ASSERT_EQUAL_STRING("WARN - no card", out);
}

void test_a_long_line_is_truncated_and_terminated(void) {
    size_t n = format(16, "AAAA", "%s", "BBBBBBBBBBBBBBBBBBBBBBBB");
    TEST_ASSERT_EQUAL_STRING("AAAABBBBBBBBBBB", out);
    TEST_ASSERT_EQUAL_UINT(15, n);
}

void test_a_prefix_longer_than_the_buffer_is_truncated(void) {
    size_t n = format(4, "PREFIX", "message");
    TEST_ASSERT_EQUAL_STRING("PRE", out);
    TEST_ASSERT_EQUAL_UINT(3, n);
}

void test_nothing_is_written_without_a_buffer(void) {
    TEST_ASSERT_EQUAL_UINT(0, format(0, "INFO - ", "hello"));
    va_list args;
    TEST_ASSERT_EQUAL_UINT(0, formatLog(nullptr, 16, "INFO - ", "hello", args));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_the_prefix_comes_first);
    RUN_TEST(test_three_strings_in_one_line);
    RUN_TEST(test_mixed_conversions);
    RUN_TEST(test_no_arguments_at_all);
    RUN_TEST(test_a_long_line_is_truncated_and_terminated);
    RUN_TEST(test_a_prefix_longer_than_the_buffer_is_truncated);
    RUN_TEST(test_nothing_is_written_without_a_buffer);
    return UNITY_END();
}
