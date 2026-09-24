// Native tests for loadConfig: the MQTT block a board takes from its image or
// from its own store.

#include <unity.h>
#include <Preferences.h>
#include "log_utils.h"
#include "settings.h"

void log(uint16_t, const char*) {}
void logf(uint16_t, const char*, ...) {}

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

void setUp(void) { Preferences().clear(); }
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

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_a_pipeline_image_logs_to_the_broker_the_board_stored);
    RUN_TEST(test_a_store_with_no_prefix_takes_the_images);
    RUN_TEST(test_an_image_with_a_broker_stores_its_whole_block);
    return UNITY_END();
}
