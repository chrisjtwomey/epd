// Native tests for which value a board uses: the image's, or its own store.

#include <unity.h>
#include "settings.h"

void setUp(void) {}
void tearDown(void) {}

void test_the_values_defaults_example_ships_are_placeholders(void) {
    TEST_ASSERT_TRUE(isPlaceholder("XXXX"));
    TEST_ASSERT_TRUE(isPlaceholder("http://YOUR_SERVER_HOST:8080/today.png"));
    TEST_ASSERT_TRUE(isPlaceholder(""));
    TEST_ASSERT_TRUE(isPlaceholder(nullptr));
}

void test_a_real_value_is_not_a_placeholder(void) {
    TEST_ASSERT_FALSE(isPlaceholder("http://192.168.1.50:8080/today.png"));
    TEST_ASSERT_FALSE(isPlaceholder("my-network"));
    TEST_ASSERT_FALSE(isPlaceholder("X"));
}

void test_the_image_wins_when_it_carries_a_real_value(void) {
    // A board flashed over USB uses what was flashed, every time.
    TEST_ASSERT_EQUAL_STRING("from-image",
                             chooseSetting("from-image", "from-store"));
}

void test_the_store_wins_when_the_image_carries_a_placeholder(void) {
    // An image built by a release pipeline cannot know these.
    TEST_ASSERT_EQUAL_STRING("from-store", chooseSetting("XXXX", "from-store"));
    TEST_ASSERT_EQUAL_STRING("from-store", chooseSetting("", "from-store"));
}

void test_with_nothing_anywhere_the_image_value_stands(void) {
    // So the failure names the placeholder rather than an empty string.
    TEST_ASSERT_EQUAL_STRING("XXXX", chooseSetting("XXXX", ""));
    TEST_ASSERT_EQUAL_STRING("XXXX", chooseSetting("XXXX", nullptr));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_the_values_defaults_example_ships_are_placeholders);
    RUN_TEST(test_a_real_value_is_not_a_placeholder);
    RUN_TEST(test_the_image_wins_when_it_carries_a_real_value);
    RUN_TEST(test_the_store_wins_when_the_image_carries_a_placeholder);
    RUN_TEST(test_with_nothing_anywhere_the_image_value_stands);
    return UNITY_END();
}
