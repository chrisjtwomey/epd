#include "settings.h"

#include <Preferences.h>

#include "log_utils.h"

// One namespace for everything this client keeps between boots.
#define SETTINGS_NAMESPACE "epd"

// Resolve one setting and keep the image's value when it is a real one, so a
// board flashed over USB provisions itself for every later image.
static String resolve(Preferences& prefs, const char* key, const char* compiled,
                      const char* label) {
    // isKey() first: getString() on an absent key logs an error of its own.
    String stored = prefs.isKey(key) ? prefs.getString(key, "") : String("");
    String chosen = chooseSetting(compiled, stored.c_str());

    if (!isPlaceholder(compiled)) {
        if (stored != chosen) {
            prefs.putString(key, chosen);
            logf(LOG_INFO, "%s stored from this image", label);
        }
    } else if (chosen == stored) {
        logf(LOG_INFO, "%s read from the store", label);
    } else {
        logf(LOG_WARNING, "%s is unset in this image and in the store", label);
    }
    return chosen;
}

// Resolve the MQTT block, which travels as a unit: see mqttSettingsAreSet.
// The strings outlive this call because the config points into them.
static void resolveMqtt(Preferences& prefs, const ClientConfig& compiled,
                        ClientConfig* cfg) {
    static String broker;
    static String clientID;
    static String topic;

    if (mqttSettingsAreSet(compiled.mqttBroker)) {
        prefs.putBool("mqttEnabled", compiled.mqttEnabled);
        prefs.putString("mqttBroker", compiled.mqttBroker);
        prefs.putInt("mqttPort", compiled.mqttPort);
        prefs.putString("mqttClientID", compiled.mqttClientID);
        prefs.putString("mqttTopic", compiled.mqttTopic);
        log(LOG_INFO, "MQTT settings stored from this image");
        return;  // cfg already holds them
    }
    if (!prefs.isKey("mqttBroker")) {
        log(LOG_INFO, "no MQTT settings in this image or the store");
        return;
    }

    broker = prefs.getString("mqttBroker", "");
    clientID = prefs.getString("mqttClientID", "");
    topic = prefs.getString("mqttTopic", "");
    cfg->mqttEnabled = prefs.getBool("mqttEnabled", cfg->mqttEnabled);
    cfg->mqttBroker = broker.c_str();
    cfg->mqttPort = prefs.getInt("mqttPort", cfg->mqttPort);
    cfg->mqttClientID = clientID.c_str();
    cfg->mqttTopic = topic.c_str();
    log(LOG_INFO, "MQTT settings read from the store");
}

ClientConfig loadConfig(const ClientConfig& compiled) {
    ClientConfig cfg = compiled;

    static String url;
    static String ssid;
    static String pass;

    Preferences prefs;
    if (!prefs.begin(SETTINGS_NAMESPACE, false)) {
        log(LOG_WARNING, "settings store unavailable; using this image's values");
        return cfg;
    }
    url = resolve(prefs, "serverURL", compiled.serverURL, "server URL");
    ssid = resolve(prefs, "wifiSSID", compiled.wifiSSID, "wifi SSID");
    pass = resolve(prefs, "wifiPass", compiled.wifiPass, "wifi password");
    resolveMqtt(prefs, compiled, &cfg);
    prefs.end();

    cfg.serverURL = url.c_str();
    cfg.wifiSSID = ssid.c_str();
    cfg.wifiPass = pass.c_str();
    return cfg;
}
