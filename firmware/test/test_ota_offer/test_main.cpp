// Native tests for the client's check on a firmware offer.

#include <unity.h>
#include "ota_offer.h"

void setUp(void) {}
void tearDown(void) {}

void test_a_different_version_with_somewhere_to_get_it(void) {
    TEST_ASSERT_TRUE(updateOffered("v1.5.1", "v1.6.0", "http://host/firmware.bin"));
}

void test_the_running_version_is_not_an_update(void) {
    TEST_ASSERT_FALSE(updateOffered("v1.6.0", "v1.6.0", "http://host/firmware.bin"));
}

void test_an_incomplete_offer_is_no_offer(void) {
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", "v1.6.0", ""));
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", "v1.6.0", nullptr));
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", "", "http://host/firmware.bin"));
    TEST_ASSERT_FALSE(updateOffered("v1.5.1", nullptr, "http://host/firmware.bin"));
}

void test_a_board_that_cannot_name_its_version_takes_the_offer(void) {
    // Nothing to compare against, and the server already decided this board
    // is eligible, so the offer stands.
    TEST_ASSERT_TRUE(updateOffered("", "v1.6.0", "http://host/firmware.bin"));
    TEST_ASSERT_TRUE(updateOffered(nullptr, "v1.6.0", "http://host/firmware.bin"));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_a_different_version_with_somewhere_to_get_it);
    RUN_TEST(test_the_running_version_is_not_an_update);
    RUN_TEST(test_an_incomplete_offer_is_no_offer);
    RUN_TEST(test_a_board_that_cannot_name_its_version_takes_the_offer);
    return UNITY_END();
}
