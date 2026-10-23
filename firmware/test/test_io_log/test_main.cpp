// Logging to the serial port and to the broker, and the lines kept while the
// broker cannot be reached. The logger keeps its broker once configured, so
// the tests that run before that come first.
#include <unity.h>

#include <string>

#include "fake_globals.h"
#include "io_test.h"
#include "log_format.h"
#include "log_utils.h"

static const char kTopic[] = "mqtt/epd/io-test";

void setUp() {
    fake::lines().clear();
    fake::broker().up = true;
    fake::broker().bufferOk = true;
    fake::broker().connects = 0;
    setLogLevel(LOG_DEBUG);
}
void tearDown() {}

static bool sentToBroker(const char* text) {
    for (const auto& line : fake::lines().broker)
        if (line.find(text) != std::string::npos) return true;
    return false;
}

static size_t brokerIndex(const char* text) {
    for (size_t i = 0; i < fake::lines().broker.size(); ++i)
        if (fake::lines().broker[i].find(text) != std::string::npos) return i;
    return (size_t)-1;
}

void test_a_line_below_the_level_is_dropped() {
    setLogLevel(LOG_WARNING);
    log(LOG_INFO, "an info line");
    logf(LOG_ERROR, "an error line %d", 7);
    TEST_ASSERT_FALSE(logged("an info line"));
    TEST_ASSERT_TRUE(logged("ERROR - an error line 7"));
}

void test_a_broker_that_does_not_answer_is_tried_then_given_up() {
    fake::broker().up = false;
    TEST_ASSERT_EQUAL(ESP_ERR_TIMEOUT, configureMQTT("broker.local", 1883, kTopic, "io-test", 2));
    TEST_ASSERT_EQUAL(3, fake::broker().connects);
    log(LOG_INFO, "still only on serial");
    TEST_ASSERT_TRUE(logged("still only on serial"));
    TEST_ASSERT_TRUE(fake::lines().broker.empty());
}

// The lines logged before the broker was reached go to it first, in order.
void test_lines_kept_while_the_broker_was_away_reach_it_first() {
    log(LOG_INFO, "kept one");
    log(LOG_INFO, "kept two");
    TEST_ASSERT_EQUAL(ESP_OK, configureMQTT("broker.local", 1883, kTopic, "io-test", 2));
    TEST_ASSERT_TRUE(brokerIndex("kept one") < brokerIndex("kept two"));
    TEST_ASSERT_TRUE(brokerIndex("kept two") < brokerIndex("connected to MQTT broker"));
    TEST_ASSERT_EQUAL(MQTT_MAX_HEADER_SIZE + 2 + strlen(kTopic) + LOG_LINE_MAX,
                      fake::broker().bufferSize);
}

void test_no_memory_for_whole_lines_says_so() {
    fake::broker().bufferOk = false;
    TEST_ASSERT_EQUAL(ESP_OK, configureMQTT("broker.local", 1883, kTopic, "io-test", 0));
    TEST_ASSERT_TRUE(logged("no memory for whole MQTT log lines"));
}

void test_a_lost_broker_is_tried_again_every_30_s_and_gets_the_lines_it_missed() {
    TEST_ASSERT_EQUAL(ESP_OK, configureMQTT("broker.local", 1883, kTopic, "io-test", 0));
    fake::broker().up = false;
    delay(30000);
    keepMQTTConnected();  // down, and due: one try, which fails
    log(LOG_INFO, "while away");
    fake::broker().connects = 0;
    fake::broker().up = true;
    keepMQTTConnected();  // up again, but the last try was just now
    TEST_ASSERT_EQUAL(0, fake::broker().connects);
    TEST_ASSERT_FALSE(sentToBroker("while away"));

    delay(30000);
    keepMQTTConnected();
    TEST_ASSERT_EQUAL(1, fake::broker().connects);
    TEST_ASSERT_TRUE(brokerIndex("while away") < brokerIndex("reconnected to the MQTT broker"));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_a_line_below_the_level_is_dropped);
    RUN_TEST(test_a_broker_that_does_not_answer_is_tried_then_given_up);
    RUN_TEST(test_lines_kept_while_the_broker_was_away_reach_it_first);
    RUN_TEST(test_no_memory_for_whole_lines_says_so);
    RUN_TEST(test_a_lost_broker_is_tried_again_every_30_s_and_gets_the_lines_it_missed);
    return UNITY_END();
}
