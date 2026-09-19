// Whether a board and a server can work together, judged by their versions.
#include <unity.h>

#include "version_compat.h"

void setUp() {}
void tearDown() {}

void test_the_same_version_matches() {
    TEST_ASSERT_EQUAL(VERSIONS_MATCH, versionsMatch("v0.2.2", "v0.2.2"));
}

void test_a_patch_never_breaks_the_contract() {
    TEST_ASSERT_EQUAL(VERSIONS_MATCH, versionsMatch("v0.2.2", "v0.2.9"));
}

void test_before_one_a_minor_breaks_it() {
    TEST_ASSERT_EQUAL(VERSIONS_DIFFER, versionsMatch("v0.2.2", "v0.3.0"));
}

void test_after_one_only_a_major_breaks_it() {
    TEST_ASSERT_EQUAL(VERSIONS_MATCH, versionsMatch("v1.2.0", "v1.7.3"));
    TEST_ASSERT_EQUAL(VERSIONS_DIFFER, versionsMatch("v1.7.3", "v2.0.0"));
}

void test_zero_and_one_differ() {
    TEST_ASSERT_EQUAL(VERSIONS_DIFFER, versionsMatch("v0.9.0", "v1.0.0"));
}

void test_what_git_describe_adds_is_ignored() {
    TEST_ASSERT_EQUAL(VERSIONS_MATCH, versionsMatch("v0.2.2-44-g2fe55a4-dirty", "v0.2.2"));
    TEST_ASSERT_EQUAL(VERSIONS_MATCH, versionsMatch("v0.2.2+build.7", "0.2.5"));
}

void test_the_v_is_optional() {
    TEST_ASSERT_EQUAL(VERSIONS_MATCH, versionsMatch("0.2.2", "V0.2.3"));
}

void test_what_is_not_a_version_cannot_be_judged() {
    TEST_ASSERT_EQUAL(VERSIONS_UNKNOWN, versionsMatch("dev", "v0.2.2"));
    TEST_ASSERT_EQUAL(VERSIONS_UNKNOWN, versionsMatch("v0.2.2", ""));
    TEST_ASSERT_EQUAL(VERSIONS_UNKNOWN, versionsMatch(nullptr, "v0.2.2"));
    TEST_ASSERT_EQUAL(VERSIONS_UNKNOWN, versionsMatch("v0.2", "v0.2.2"));
    TEST_ASSERT_EQUAL(VERSIONS_UNKNOWN, versionsMatch("v0.2.2garbage", "v0.2.2"));
    TEST_ASSERT_EQUAL(VERSIONS_UNKNOWN, versionsMatch("2fe55a4", "v0.2.2"));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_the_same_version_matches);
    RUN_TEST(test_a_patch_never_breaks_the_contract);
    RUN_TEST(test_before_one_a_minor_breaks_it);
    RUN_TEST(test_after_one_only_a_major_breaks_it);
    RUN_TEST(test_zero_and_one_differ);
    RUN_TEST(test_what_git_describe_adds_is_ignored);
    RUN_TEST(test_the_v_is_optional);
    RUN_TEST(test_what_is_not_a_version_cannot_be_judged);
    return UNITY_END();
}
