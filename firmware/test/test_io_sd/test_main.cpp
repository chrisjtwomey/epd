// A board with an SD card: settings from config.yaml, parsed by the real
// YAMLDuino, and a page written to the card and drawn from it.
#include <unity.h>

#include <string>

#include "MockBoard.h"
#include "epd.h"
#include "fake_globals.h"
#include "file_utils.h"
#include "image.h"
#include "io_test.h"
#include "sd_config.h"

static MockBoard board;
static std::string card;

static const char kWhole[] =
    "server:\n"
    "  url: http://server:8080/today.png\n"
    "  retries: 3\n"
    "  default_refresh_seconds: 1800\n"
    "wifi:\n"
    "  ssid: home\n"
    "  pass: secret\n"
    "  connect_timeout_seconds: 7\n"
    "mqtt_logger:\n"
    "  enabled: true\n"
    "  broker: broker.local\n"
    "  port: 1884\n"
    "  clientId: kitchen\n"
    "  prefix: mqtt/epd\n"
    "  retries: 2\n";

static ClientConfig builtIn() {
    ClientConfig cfg = {};
    cfg.serverURL = "http://built-in/";
    cfg.serverRetries = 1;
    cfg.defaultRefreshSeconds = 3600;
    cfg.wifiSSID = "built-in";
    cfg.wifiPass = "built-in";
    cfg.wifiConnectTimeoutSeconds = 10;
    cfg.mqttBroker = "built-in.local";
    cfg.mqttPort = 1883;
    cfg.mqttClientID = "built-in";
    cfg.mqttPrefix = "built-in";
    return cfg;
}

static ClientConfig fromCard(const std::string& text) {
    card = text;
    board.sdReadFileContent = card.c_str();
    ClientConfig cfg = builtIn();
    TEST_ASSERT_TRUE(applySdConfig(&cfg));
    return cfg;
}

void setUp() {
    board = MockBoard();
    epdBegin(board);
    fake::lines().clear();
}
void tearDown() {}

void test_a_board_without_a_card_keeps_its_own_settings() {
    board.sdCardInitReturn = false;
    ClientConfig cfg = builtIn();
    TEST_ASSERT_FALSE(applySdConfig(&cfg));
    TEST_ASSERT_EQUAL_STRING("built-in", cfg.wifiSSID);
    TEST_ASSERT_TRUE(logged("no SD card"));
}

void test_a_card_without_a_config_file_changes_nothing() {
    ClientConfig cfg = builtIn();
    TEST_ASSERT_TRUE(applySdConfig(&cfg));
    TEST_ASSERT_EQUAL_STRING("built-in", cfg.wifiSSID);
    TEST_ASSERT_TRUE(logged("cannot read the config file on the card"));
}

void test_every_setting_on_the_card_wins() {
    const ClientConfig cfg = fromCard(kWhole);
    TEST_ASSERT_EQUAL_STRING("http://server:8080/today.png", cfg.serverURL);
    TEST_ASSERT_EQUAL(3, cfg.serverRetries);
    TEST_ASSERT_EQUAL(1800, cfg.defaultRefreshSeconds);
    TEST_ASSERT_EQUAL_STRING("home", cfg.wifiSSID);
    TEST_ASSERT_EQUAL_STRING("secret", cfg.wifiPass);
    TEST_ASSERT_EQUAL(7, cfg.wifiConnectTimeoutSeconds);
    TEST_ASSERT_TRUE(cfg.mqttEnabled);
    TEST_ASSERT_EQUAL_STRING("broker.local", cfg.mqttBroker);
    TEST_ASSERT_EQUAL(1884, cfg.mqttPort);
    TEST_ASSERT_EQUAL_STRING("kitchen", cfg.mqttClientID);
    TEST_ASSERT_EQUAL_STRING("mqtt/epd", cfg.mqttPrefix);
    TEST_ASSERT_EQUAL(2, cfg.mqttRetries);
}

void test_a_setting_the_card_leaves_out_keeps_its_built_in_value() {
    const ClientConfig cfg = fromCard(
        "server:\n  url: http://server/\nwifi:\n  ssid: home\n  pass: secret\n");
    TEST_ASSERT_EQUAL(1, cfg.serverRetries);
    TEST_ASSERT_EQUAL(10, cfg.wifiConnectTimeoutSeconds);
    TEST_ASSERT_EQUAL_STRING("built-in.local", cfg.mqttBroker);
}

void test_a_card_without_a_required_key_is_ignored() {
    const ClientConfig cfg = fromCard("server:\n  url: http://server/\nwifi:\n  ssid: home\n");
    TEST_ASSERT_EQUAL_STRING("built-in", cfg.wifiSSID);
    TEST_ASSERT_EQUAL_STRING("http://built-in/", cfg.serverURL);
    TEST_ASSERT_TRUE(logged("config file is missing required keys"));
}

void test_a_card_that_is_not_yaml_is_ignored_not_a_crash() {
    const ClientConfig cfg = fromCard("server: [unclosed\n");
    TEST_ASSERT_EQUAL_STRING("built-in", cfg.wifiSSID);
    TEST_ASSERT_TRUE(logged("config file is not valid YAML: Failed to load yaml document!"));
}

// YAML cut short still parses, so a file too long to read whole is refused.
void test_a_config_file_too_long_to_read_whole_is_ignored() {
    std::string text = kWhole;
    text.append(1536 - text.size(), '#');
    ClientConfig cfg = fromCard(text);
    TEST_ASSERT_EQUAL_STRING("home", cfg.wifiSSID);
    text += "#";
    cfg = fromCard(text);
    TEST_ASSERT_EQUAL_STRING("built-in", cfg.wifiSSID);
    TEST_ASSERT_TRUE(logged("config file is too long: the most is 1536 bytes"));
}

// broker, clientId and prefix name one broker, so they come together.
void test_part_of_a_broker_on_the_card_keeps_the_boards_own() {
    const ClientConfig cfg = fromCard(
        "server:\n  url: http://server/\nwifi:\n  ssid: home\n  pass: secret\n"
        "mqtt_logger:\n  broker: broker.local\n");
    TEST_ASSERT_EQUAL_STRING("built-in.local", cfg.mqttBroker);
    TEST_ASSERT_TRUE(logged("card mqtt_logger ignored"));
}

void test_a_page_is_written_to_the_card_and_drawn_from_it() {
    uint8_t page[] = "PNG";
    TEST_ASSERT_EQUAL(ESP_OK, writeFile(page, 3, IMAGE_RW_PATH));
    TEST_ASSERT_EQUAL(ESP_OK, drawImage(IMAGE_RW_PATH));
    board.sdWriteFileReturn = false;
    board.drawPngReturn = false;
    TEST_ASSERT_EQUAL(ESP_ERR_EFILEW, writeFile(page, 3, IMAGE_RW_PATH));
    TEST_ASSERT_EQUAL(ESP_ERR_EDRAW, drawImage(IMAGE_RW_PATH));
}

// A card from before the rename keeps the board's own wait, and says why.
void test_a_card_with_the_old_wifi_retries_key_is_told_its_new_name() {
    const ClientConfig cfg = fromCard(
        "server:\n  url: http://server/\nwifi:\n  ssid: home\n  pass: secret\n  retries: 7\n");
    TEST_ASSERT_EQUAL(10, cfg.wifiConnectTimeoutSeconds);
    TEST_ASSERT_TRUE(logged("card wifi.retries ignored: it is wifi.connect_timeout_seconds now"));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_a_board_without_a_card_keeps_its_own_settings);
    RUN_TEST(test_a_card_without_a_config_file_changes_nothing);
    RUN_TEST(test_every_setting_on_the_card_wins);
    RUN_TEST(test_a_setting_the_card_leaves_out_keeps_its_built_in_value);
    RUN_TEST(test_a_card_without_a_required_key_is_ignored);
    RUN_TEST(test_a_card_that_is_not_yaml_is_ignored_not_a_crash);
    RUN_TEST(test_a_config_file_too_long_to_read_whole_is_ignored);
    RUN_TEST(test_part_of_a_broker_on_the_card_keeps_the_boards_own);
    RUN_TEST(test_a_card_with_the_old_wifi_retries_key_is_told_its_new_name);
    RUN_TEST(test_a_page_is_written_to_the_card_and_drawn_from_it);
    return UNITY_END();
}
