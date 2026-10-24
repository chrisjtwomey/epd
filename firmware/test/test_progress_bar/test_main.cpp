// The update bar: one full draw, then a partial update for
// each step it gains, and never more than ten of those.
#include <unity.h>

#include "progress_bar.h"

static const int kTotal = 1200000;

void setUp() {}
void tearDown() {}

void test_the_first_call_draws_the_whole_panel_with_an_empty_bar() {
    ProgressBar bar;
    TEST_ASSERT_EQUAL(ProgressBar::FULL, bar.update(0, kTotal));
    TEST_ASSERT_EQUAL(0, bar.filled);
}

void test_bytes_that_do_not_reach_a_step_push_nothing() {
    ProgressBar bar;
    bar.update(0, kTotal);
    TEST_ASSERT_EQUAL(ProgressBar::NONE, bar.update(kTotal / 20, kTotal));
    TEST_ASSERT_EQUAL(0, bar.filled);
}

void test_each_step_gained_is_one_partial_update() {
    ProgressBar bar;
    bar.update(0, kTotal);
    TEST_ASSERT_EQUAL(ProgressBar::PARTIAL, bar.update(kTotal / 10, kTotal));
    TEST_ASSERT_EQUAL(1, bar.filled);
    TEST_ASSERT_EQUAL(ProgressBar::PARTIAL, bar.update(kTotal / 2, kTotal));
    TEST_ASSERT_EQUAL(5, bar.filled);
}

void test_a_whole_update_takes_at_most_ten_partial_updates() {
    ProgressBar bar;
    int partial = 0;
    bar.update(0, kTotal);
    for (int done = 0; done <= kTotal; done += 4096)
        if (bar.update(done, kTotal) == ProgressBar::PARTIAL) ++partial;
    if (bar.update(kTotal, kTotal) == ProgressBar::PARTIAL) ++partial;
    TEST_ASSERT_EQUAL(10, partial);
    TEST_ASSERT_EQUAL(ProgressBar::kSteps, bar.filled);
}

void test_an_unknown_total_draws_an_empty_bar_and_waits() {
    ProgressBar bar;
    TEST_ASSERT_EQUAL(ProgressBar::FULL, bar.update(50000, 0));
    TEST_ASSERT_EQUAL(0, bar.filled);
    TEST_ASSERT_EQUAL(ProgressBar::NONE, bar.update(90000, 0));
}

void test_the_bar_never_goes_back() {
    ProgressBar bar;
    bar.update(0, kTotal);
    bar.update(kTotal / 2, kTotal);
    TEST_ASSERT_EQUAL(ProgressBar::NONE, bar.update(kTotal / 4, kTotal));
    TEST_ASSERT_EQUAL(5, bar.filled);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_the_first_call_draws_the_whole_panel_with_an_empty_bar);
    RUN_TEST(test_bytes_that_do_not_reach_a_step_push_nothing);
    RUN_TEST(test_each_step_gained_is_one_partial_update);
    RUN_TEST(test_a_whole_update_takes_at_most_ten_partial_updates);
    RUN_TEST(test_an_unknown_total_draws_an_empty_bar_and_waits);
    RUN_TEST(test_the_bar_never_goes_back);
    return UNITY_END();
}
