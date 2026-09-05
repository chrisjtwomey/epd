// Native tests for the client's check on a firmware offer.

#include <unity.h>
#include "ota_offer.h"

void setUp(void) {}
void tearDown(void) {}

static const char* URL = "http://host/firmware.bin";

void test_a_different_version_with_somewhere_to_get_it(void) {
    TEST_ASSERT_TRUE(updateOffered("v1.5.1", "v1.6.0", URL, ""));
}

void test_the_running_version_is_not_an_update(void) {
    TEST_ASSERT_FALSE(updateOffered("v1.6.0", "v1.6.0", URL, ""));
}

void test_an_incomplete_offer_is_no_offer(void) {
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", "v1.6.0", "", ""));
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", "v1.6.0", nullptr, ""));
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", "", URL, ""));
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", nullptr, URL, ""));
}

void test_a_board_that_cannot_name_its_version_takes_the_offer(void) {
    // Nothing to compare against, and the server already decided this board
    // is eligible, so the offer stands.
    TEST_ASSERT_TRUE(updateOffered("", "v1.6.0", URL, ""));
    TEST_ASSERT_TRUE(updateOffered(nullptr, "v1.6.0", URL, ""));
}

void test_an_image_that_already_rolled_back_is_refused(void) {
    // Otherwise a bad release loops: roll back, be offered it, take it again.
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", "v1.6.0", URL, "v1.6.0"));
    TEST_ASSERT_TRUE(updateOffered("v1.5.1", "v1.7.0", URL, "v1.6.0"));
}

void test_the_refusal_can_be_named_for_the_log(void) {
    TEST_ASSERT_TRUE(updateRefusedBefore("v1.6.0", "v1.6.0"));
    TEST_ASSERT_FALSE(updateRefusedBefore("v1.7.0", "v1.6.0"));
    TEST_ASSERT_FALSE(updateRefusedBefore("v1.6.0", ""));
    TEST_ASSERT_FALSE(updateRefusedBefore("", "v1.6.0"));
    TEST_ASSERT_FALSE(updateRefusedBefore(nullptr, nullptr));
}

void test_no_rejected_version_refuses_nothing(void) {
    TEST_ASSERT_TRUE(updateOffered("v1.5.1", "v1.6.0", URL, nullptr));
    TEST_ASSERT_TRUE(updateOffered("v1.5.1", "v1.6.0", URL, ""));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_a_different_version_with_somewhere_to_get_it);
    RUN_TEST(test_the_running_version_is_not_an_update);
    RUN_TEST(test_an_incomplete_offer_is_no_offer);
    RUN_TEST(test_a_board_that_cannot_name_its_version_takes_the_offer);
    RUN_TEST(test_an_image_that_already_rolled_back_is_refused);
    RUN_TEST(test_no_rejected_version_refuses_nothing);
    RUN_TEST(test_the_refusal_can_be_named_for_the_log);
    return UNITY_END();
}
