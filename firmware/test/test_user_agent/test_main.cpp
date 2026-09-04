// Native tests for the User-Agent the client sends with every download.

#include <unity.h>
#include <string.h>
#include "user_agent.h"

static char buf[64];

void setUp(void) {
    memset(buf, 'x', sizeof(buf));
}

void tearDown(void) {}

void test_product_version_and_device(void) {
    int n = buildUserAgent(buf, sizeof(buf), "inkplate10-weather-cal", "v1.4.0", "Inkplate10");
    TEST_ASSERT_EQUAL_STRING("inkplate10-weather-cal/v1.4.0 (Inkplate10)", buf);
    TEST_ASSERT_EQUAL_INT((int)strlen(buf), n);
}

void test_no_device_means_no_comment(void) {
    buildUserAgent(buf, sizeof(buf), "EpdClient", "dev", nullptr);
    TEST_ASSERT_EQUAL_STRING("EpdClient/dev", buf);
    buildUserAgent(buf, sizeof(buf), "EpdClient", "dev", "");
    TEST_ASSERT_EQUAL_STRING("EpdClient/dev", buf);
}

void test_small_buffer_is_truncated_and_terminated(void) {
    char small[8];
    int n = buildUserAgent(small, sizeof(small), "EpdClient", "v1", "Inkplate10");
    TEST_ASSERT_EQUAL_STRING("EpdClie", small);
    TEST_ASSERT_EQUAL_INT((int)strlen("EpdClient/v1 (Inkplate10)"), n);
}

void test_client_user_agent_uses_the_build_defines(void) {
    // The library's own test build sets neither define, so the defaults apply.
    TEST_ASSERT_EQUAL_STRING("EpdClient/dev (Inkplate5V2)", clientUserAgent("Inkplate5V2"));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_product_version_and_device);
    RUN_TEST(test_no_device_means_no_comment);
    RUN_TEST(test_small_buffer_is_truncated_and_terminated);
    RUN_TEST(test_client_user_agent_uses_the_build_defines);
    return UNITY_END();
}
