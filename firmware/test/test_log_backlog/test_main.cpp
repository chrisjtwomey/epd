// The log lines a board keeps while its broker is unreachable.
#include <unity.h>
#include <cstring>

#include "log_backlog.h"

void setUp() {}
void tearDown() {}

static const size_t kLines = 3;
static const size_t kBytes = 8;

void test_lines_come_back_oldest_first() {
    char slots[kLines * kBytes];
    LogBacklog b(slots, kLines, kBytes);
    b.push("one");
    b.push("two");
    char out[kBytes];
    TEST_ASSERT_EQUAL(2, b.count());
    TEST_ASSERT_TRUE(b.pop(out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("one", out);
    TEST_ASSERT_TRUE(b.pop(out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("two", out);
    TEST_ASSERT_FALSE(b.pop(out, sizeof(out)));
}

void test_a_full_backlog_drops_its_oldest_line() {
    char slots[kLines * kBytes];
    LogBacklog b(slots, kLines, kBytes);
    b.push("1");
    b.push("2");
    b.push("3");
    b.push("4");
    TEST_ASSERT_EQUAL(kLines, b.count());
    char out[kBytes];
    b.pop(out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("2", out);
    b.pop(out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("3", out);
    b.pop(out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("4", out);
}

void test_a_long_line_is_cut_to_its_slot() {
    char slots[kLines * kBytes];
    LogBacklog b(slots, kLines, kBytes);
    b.push("abcdefghijkl");
    char out[16];
    TEST_ASSERT_TRUE(b.pop(out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("abcdefg", out);
}

void test_a_short_out_buffer_gets_a_cut_line() {
    char slots[kLines * kBytes];
    LogBacklog b(slots, kLines, kBytes);
    b.push("abcdefg");
    char out[4];
    TEST_ASSERT_TRUE(b.pop(out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("abc", out);
}

void test_lines_keep_their_order_across_the_wrap() {
    char slots[kLines * kBytes];
    LogBacklog b(slots, kLines, kBytes);
    char out[kBytes];
    for (int round = 0; round < 5; ++round) {
        b.push("a");
        b.push("b");
        b.pop(out, sizeof(out));
        TEST_ASSERT_EQUAL_STRING("a", out);
        b.pop(out, sizeof(out));
        TEST_ASSERT_EQUAL_STRING("b", out);
    }
    TEST_ASSERT_EQUAL(0, b.count());
}

void test_a_backlog_with_no_slots_keeps_nothing() {
    LogBacklog b(nullptr, 0, kBytes);
    b.push("one");
    char out[kBytes];
    TEST_ASSERT_EQUAL(0, b.count());
    TEST_ASSERT_FALSE(b.pop(out, sizeof(out)));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_lines_come_back_oldest_first);
    RUN_TEST(test_a_full_backlog_drops_its_oldest_line);
    RUN_TEST(test_a_long_line_is_cut_to_its_slot);
    RUN_TEST(test_a_short_out_buffer_gets_a_cut_line);
    RUN_TEST(test_lines_keep_their_order_across_the_wrap);
    RUN_TEST(test_a_backlog_with_no_slots_keeps_nothing);
    return UNITY_END();
}
