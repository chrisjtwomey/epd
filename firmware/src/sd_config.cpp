#include "sd_config.h"

#if defined(USE_SDCARD)

#include <ArduinoJson.h>
#include <ArduinoYaml.h>

#include "IBoard.h"
#include "file_utils.h"
#include "log_utils.h"

// Upper bound on config.yaml. The parsed document is a StaticJsonDocument<768>,
// so a config large enough to overflow this would not fit the document either.
#define CONFIG_BUFFER_SIZE 1536

// Provided by main.cpp (firmware) or test_main.cpp (tests).
extern IBoard& board;

// Read the card and apply what it says. Every problem is a warning, and
// leaves cfg untouched.
static void readCard(ClientConfig* cfg) {
    // Read the config file through IBoard so this code stays independent of
    // any particular SD library.
    uint8_t configBuf[CONFIG_BUFFER_SIZE];
    if (board.sdReadFile(CONFIG_FILE_PATH, configBuf, sizeof(configBuf)) == 0) {
        log(LOG_WARNING, "cannot read the config file on the card");
        return;
    }

    StaticJsonDocument<768> doc;
    DeserializationError parsed = deserializeYml(doc, (const char*)configBuf);
    if (parsed) {
        logf(LOG_WARNING, "failed to deserialize YAML: %s", parsed.c_str());
        return;
    }

    JsonObject serverCfg = doc["server"];
    JsonObject wifiCfg = doc["wifi"];
    JsonObject ntpCfg = doc["ntp"];

    const char* cfgServerURL = serverCfg["url"];
    const char* cfgWifiSSID = wifiCfg["ssid"];
    const char* cfgWifiPass = wifiCfg["pass"];
    const char* cfgNtpHost = ntpCfg["host"];
    const char* cfgNtpTimezone = ntpCfg["timezone"];

    if (!cfgServerURL || !cfgWifiSSID || !cfgWifiPass || !cfgNtpHost || !cfgNtpTimezone) {
        log(LOG_WARNING, "config file is missing required keys");
        return;
    }

    // The document goes out of scope with this function, so the strings the
    // config points at have to outlive it.
    static String sdServerURL;
    static String sdWifiSSID;
    static String sdWifiPass;
    static String sdNtpHost;
    static String sdNtpTimezone;
    static String sdMqttBroker;
    static String sdMqttClientID;
    static String sdMqttTopic;

    sdServerURL = cfgServerURL;
    sdWifiSSID = cfgWifiSSID;
    sdWifiPass = cfgWifiPass;
    sdNtpHost = cfgNtpHost;
    sdNtpTimezone = cfgNtpTimezone;

    cfg->serverURL = sdServerURL.c_str();
    cfg->serverRetries = serverCfg["retries"] | cfg->serverRetries;
    cfg->defaultRefreshSeconds =
        serverCfg["default_refresh_seconds"] | cfg->defaultRefreshSeconds;

    cfg->wifiSSID = sdWifiSSID.c_str();
    cfg->wifiPass = sdWifiPass.c_str();
    cfg->wifiRetries = wifiCfg["retries"] | cfg->wifiRetries;

    cfg->ntpHost = sdNtpHost.c_str();
    cfg->ntpTimezone = sdNtpTimezone.c_str();

    JsonObject mqttCfg = doc["mqtt_logger"];
    cfg->mqttEnabled = mqttCfg["enabled"] | cfg->mqttEnabled;
    if (mqttCfg["broker"] && mqttCfg["clientId"] && mqttCfg["topic"]) {
        sdMqttBroker = mqttCfg["broker"].as<const char*>();
        sdMqttClientID = mqttCfg["clientId"].as<const char*>();
        sdMqttTopic = mqttCfg["topic"].as<const char*>();
        cfg->mqttBroker = sdMqttBroker.c_str();
        cfg->mqttClientID = sdMqttClientID.c_str();
        cfg->mqttTopic = sdMqttTopic.c_str();
    }
    cfg->mqttPort = mqttCfg["port"] | cfg->mqttPort;
    cfg->mqttRetries = mqttCfg["retries"] | cfg->mqttRetries;
}

bool applySdConfig(ClientConfig* cfg) {
    // A card is optional: one image serves boards with and without one.
    if (!board.sdCardInit()) {
        log(LOG_WARNING, "no SD card; using this board's own settings");
        return false;
    }
    readCard(cfg);
    return true;
}

#else

bool applySdConfig(ClientConfig*) { return false; }

#endif  // USE_SDCARD
