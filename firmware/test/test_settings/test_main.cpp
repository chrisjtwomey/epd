// Native tests for loadConfig: the MQTT block a board takes from its image or
// from its own store.

#include <unity.h>
#include <Preferences.h>

#include <string.h>

#include <string>
#include <vector>

#include "log_utils.h"
#include "settings.h"
#include "settings_store.h"

// Each line logged since the last clear, by its format.
static std::vector<std::string> logged;
void log(uint16_t, const char* msg) { logged.push_back(msg); }
void logf(uint16_t, const char* fmt, ...) { logged.push_back(fmt); }

static bool loggedLine(const char* text) {
    for (const std::string& line : logged)
        if (strstr(line.c_str(), text)) return true;
    return false;
}

// An image built by a release pipeline: no broker, but its product's prefix.
static ClientConfig pipelineImage() {
    ClientConfig cfg = {};
    cfg.serverURL = "http://192.168.1.20:8080/today.png";
    cfg.wifiSSID = "my-network";
    cfg.wifiPass = "secret";
    cfg.mqttBroker = "XXXX";
    cfg.mqttClientID = "XXXX";
    cfg.mqttPrefix = "mqtt/canary";
    return cfg;
}

static void storeMqttBlock() {
    Preferences prefs;
    prefs.putBool("mqttEnabled", true);
    prefs.putString("mqttBroker", "192.168.1.10");
    prefs.putInt("mqttPort", 1883);
    prefs.putString("mqttClientID", "canary-head");
}

void setUp(void) {
    Preferences().clear();
    logged.clear();
}
void tearDown(void) {}

void test_a_pipeline_image_logs_to_the_broker_the_board_stored(void) {
    storeMqttBlock();
    Preferences().putString("mqttPrefix", "mqtt/stored");
    ClientConfig cfg = loadConfig(pipelineImage());
    TEST_ASSERT_TRUE(cfg.mqttEnabled);
    TEST_ASSERT_EQUAL_STRING("192.168.1.10", cfg.mqttBroker);
    TEST_ASSERT_EQUAL_INT(1883, cfg.mqttPort);
    TEST_ASSERT_EQUAL_STRING("canary-head", cfg.mqttClientID);
    TEST_ASSERT_EQUAL_STRING("mqtt/stored", cfg.mqttPrefix);
}

void test_a_store_with_no_prefix_takes_the_images(void) {
    storeMqttBlock();
    ClientConfig cfg = loadConfig(pipelineImage());
    TEST_ASSERT_EQUAL_STRING("192.168.1.10", cfg.mqttBroker);
    TEST_ASSERT_EQUAL_STRING("mqtt/canary", cfg.mqttPrefix);
}

void test_an_image_with_a_broker_stores_its_whole_block(void) {
    ClientConfig image = pipelineImage();
    image.mqttEnabled = true;
    image.mqttBroker = "192.168.1.10";
    image.mqttPort = 1883;
    image.mqttClientID = "canary-head";
    loadConfig(image);
    ClientConfig cfg = loadConfig(pipelineImage());
    TEST_ASSERT_EQUAL_STRING("192.168.1.10", cfg.mqttBroker);
    TEST_ASSERT_EQUAL_STRING("mqtt/canary", cfg.mqttPrefix);
    TEST_ASSERT_EQUAL_STRING("mqtt/canary", Preferences().getString("mqttPrefix", "").c_str());
}

static ClientConfig brokerImage(const char* broker) {
    ClientConfig image = pipelineImage();
    image.mqttEnabled = true;
    image.mqttBroker = broker;
    image.mqttPort = 1883;
    image.mqttClientID = "canary-head";
    return image;
}

void test_an_image_whose_block_is_stored_already_logs_no_store(void) {
    loadConfig(brokerImage("192.168.1.10"));
    logged.clear();
    loadConfig(brokerImage("192.168.1.10"));
    TEST_ASSERT_FALSE(loggedLine("MQTT settings stored"));
}

void test_an_image_with_a_new_broker_stores_it_and_says_so(void) {
    loadConfig(brokerImage("192.168.1.10"));
    logged.clear();
    loadConfig(brokerImage("192.168.1.11"));
    TEST_ASSERT_TRUE(loggedLine("MQTT settings stored"));
    TEST_ASSERT_EQUAL_STRING("192.168.1.11", Preferences().getString("mqttBroker", "").c_str());
}

void test_a_board_without_a_stored_key_has_none(void) {
    Preferences().clear();
    TEST_ASSERT_FALSE(loadBoardKey().present);
}

void test_a_stored_key_is_read_back_with_its_id(void) {
    Preferences().clear();
    uint8_t key[BOARD_KEY_LEN];
    for (int i = 0; i < BOARD_KEY_LEN; ++i) key[i] = (uint8_t)i;
    TEST_ASSERT_TRUE(storeBoardKey(key));
    const BoardKey kept = loadBoardKey();
    TEST_ASSERT_TRUE(kept.present);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(key, kept.key, BOARD_KEY_LEN);
    TEST_ASSERT_EQUAL_STRING("630dcd2966c43366", kept.id);
}

void test_a_stored_key_of_the_wrong_length_counts_as_none(void) {
    Preferences().clear();
    Preferences().putBytes("boardKey", "short", 5);
    TEST_ASSERT_FALSE(loadBoardKey().present);
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_a_board_without_a_stored_key_has_none);
    RUN_TEST(test_a_stored_key_is_read_back_with_its_id);
    RUN_TEST(test_a_stored_key_of_the_wrong_length_counts_as_none);
    RUN_TEST(test_a_pipeline_image_logs_to_the_broker_the_board_stored);
    RUN_TEST(test_a_store_with_no_prefix_takes_the_images);
    RUN_TEST(test_an_image_with_a_broker_stores_its_whole_block);
    RUN_TEST(test_an_image_whose_block_is_stored_already_logs_no_store);
    RUN_TEST(test_an_image_with_a_new_broker_stores_it_and_says_so);
    return UNITY_END();
}
