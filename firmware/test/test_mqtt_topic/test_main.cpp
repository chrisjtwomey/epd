// Native tests for the topic a board publishes its log lines to.

#include <unity.h>
#include <string.h>
#include "mqtt_topic.h"

static char buf[32];

void setUp(void) {
    memset(buf, 'x', sizeof(buf));
}

void tearDown(void) {}

void test_prefix_then_board(void) {
    size_t n = boardLogTopic("mqtt/canary", "canary-dock", buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("mqtt/canary/canary-dock", buf);
    TEST_ASSERT_EQUAL_UINT((unsigned)strlen(buf), (unsigned)n);
}

void test_a_topic_that_does_not_fit_writes_nothing(void) {
    TEST_ASSERT_EQUAL_UINT(0, (unsigned)boardLogTopic("mqtt/canary", "canary-dock", buf, 12));
    TEST_ASSERT_EQUAL_STRING("", buf);
}

void test_no_room_at_all(void) {
    TEST_ASSERT_EQUAL_UINT(0, (unsigned)boardLogTopic("p", "b", buf, 0));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_prefix_then_board);
    RUN_TEST(test_a_topic_that_does_not_fit_writes_nothing);
    RUN_TEST(test_no_room_at_all);
    return UNITY_END();
}
