#include "settings.h"

#include <Preferences.h>

#include "defaults.h"
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

ClientConfig loadConfig() {
    ClientConfig cfg = {
        serverURL, serverRetries, serverDefaultRefreshSeconds,
        wifiSSID, wifiPass, wifiRetries,
        ntpHost, ntpTimezone,
        mqttLoggerEnabled, mqttLoggerBroker, mqttLoggerPort,
        mqttLoggerClientID, mqttLoggerTopic, mqttLoggerRetries,
    };

    static String url;
    static String ssid;
    static String pass;

    Preferences prefs;
    if (!prefs.begin(SETTINGS_NAMESPACE, false)) {
        log(LOG_WARNING, "settings store unavailable; using this image's values");
        return cfg;
    }
    url = resolve(prefs, "serverURL", serverURL, "server URL");
    ssid = resolve(prefs, "wifiSSID", wifiSSID, "wifi SSID");
    pass = resolve(prefs, "wifiPass", wifiPass, "wifi password");
    prefs.end();

    cfg.serverURL = url.c_str();
    cfg.wifiSSID = ssid.c_str();
    cfg.wifiPass = pass.c_str();
    return cfg;
}
