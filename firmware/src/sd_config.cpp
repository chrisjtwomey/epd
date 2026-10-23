#include "sd_config.h"

#if defined(USE_SDCARD)

#include <ArduinoJson.h>
#include <ArduinoYaml.h>

#include <exception>

#include "epd.h"
#include "file_utils.h"
#include "log_utils.h"

// The longest config.yaml the board reads. The parsed document grows on the
// heap as it needs, so this is the only bound on the card's config.
static const size_t kMaxConfigBytes = 1536;


// YAMLDuino throws on a file it cannot parse. Uncaught, that is abort() and
// a reboot at every boot; caught, it is a warning like any other fault in
// the file.
static bool parseYaml(const char* text, JsonDocument& doc) {
    DeserializationError parsed;
#if defined(__cpp_exceptions)
    try {
        parsed = deserializeYml(doc, text);
    } catch (const std::exception& e) {
        logf(LOG_WARNING, "config file is not valid YAML: %s", e.what());
        return false;
    }
#else
    parsed = deserializeYml(doc, text);
#endif
    if (parsed) {
        logf(LOG_WARNING, "failed to deserialize YAML: %s", parsed.c_str());
        return false;
    }
    return true;
}

// Read the card and apply what it says. Every problem is a warning, and
// leaves cfg untouched.
static void readCard(ClientConfig* cfg) {
    // Read the config file through IBoard so this code stays independent of
    // any particular SD library.
    // Room for one byte past the longest file, and the terminator: a read that
    // fills it is a file too long to read whole.
    uint8_t configBuf[kMaxConfigBytes + 2];
    size_t configLen = epdBoard().sdReadFile(CONFIG_FILE_PATH, configBuf, sizeof(configBuf));
    if (configLen == 0) {
        log(LOG_WARNING, "cannot read the config file on the card");
        return;
    }
    // YAML cut short still parses, and a value cut part way would pass as a
    // whole one, such as the Wi-Fi password.
    if (configLen > kMaxConfigBytes) {
        logf(LOG_WARNING, "config file is too long: the most is %u bytes",
             (unsigned)kMaxConfigBytes);
        return;
    }
    configBuf[configLen] = '\0';

    JsonDocument doc;
    if (!parseYaml((const char*)configBuf, doc)) return;

    JsonObject serverCfg = doc["server"];
    JsonObject wifiCfg = doc["wifi"];

    const char* cfgServerURL = serverCfg["url"];
    const char* cfgWifiSSID = wifiCfg["ssid"];
    const char* cfgWifiPass = wifiCfg["pass"];

    if (!cfgServerURL || !cfgWifiSSID || !cfgWifiPass) {
        log(LOG_WARNING, "config file is missing required keys");
        return;
    }

    // The document goes out of scope with this function, so the strings the
    // config points at have to outlive it.
    static String sdServerURL;
    static String sdWifiSSID;
    static String sdWifiPass;
    static String sdMqttBroker;
    static String sdMqttClientID;
    static String sdMqttPrefix;

    sdServerURL = cfgServerURL;
    sdWifiSSID = cfgWifiSSID;
    sdWifiPass = cfgWifiPass;

    cfg->serverURL = sdServerURL.c_str();
    cfg->serverRetries = serverCfg["retries"] | cfg->serverRetries;
    cfg->defaultRefreshSeconds =
        serverCfg["default_refresh_seconds"] | cfg->defaultRefreshSeconds;

    cfg->wifiSSID = sdWifiSSID.c_str();
    cfg->wifiPass = sdWifiPass.c_str();
    cfg->wifiRetries = wifiCfg["retries"] | cfg->wifiRetries;

    JsonObject mqttCfg = doc["mqtt_logger"];
    cfg->mqttEnabled = mqttCfg["enabled"] | cfg->mqttEnabled;
    if (mqttCfg["broker"] && mqttCfg["clientId"] && mqttCfg["prefix"]) {
        sdMqttBroker = mqttCfg["broker"].as<const char*>();
        sdMqttClientID = mqttCfg["clientId"].as<const char*>();
        sdMqttPrefix = mqttCfg["prefix"].as<const char*>();
        cfg->mqttBroker = sdMqttBroker.c_str();
        cfg->mqttClientID = sdMqttClientID.c_str();
        cfg->mqttPrefix = sdMqttPrefix.c_str();
    } else if (mqttCfg["broker"] || mqttCfg["clientId"] || mqttCfg["prefix"]) {
        log(LOG_WARNING, "card mqtt_logger ignored: it needs broker, clientId and prefix");
    }
    cfg->mqttPort = mqttCfg["port"] | cfg->mqttPort;
    cfg->mqttRetries = mqttCfg["retries"] | cfg->mqttRetries;
}

bool applySdConfig(ClientConfig* cfg) {
    // A build with USE_SDCARD expects a card. A missing one is only a warning,
    // so a board that loses its card still starts.
    if (!epdBoard().sdCardInit()) {
        log(LOG_WARNING, "no SD card; using this board's own settings");
        return false;
    }
    readCard(cfg);
    return true;
}

#else

bool applySdConfig(ClientConfig*) { return false; }

#endif  // USE_SDCARD
