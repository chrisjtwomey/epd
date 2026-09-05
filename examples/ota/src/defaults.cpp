#include "EpdClient.h"

ClientConfig builtInSettings() {
    ClientConfig cfg = {};

    cfg.serverURL = "http://YOUR_SERVER_HOST:8080/clock.png";
    cfg.wifiSSID = "XXXX";
    cfg.wifiPass = "XXXX";

    cfg.serverRetries = 3;
    cfg.defaultRefreshSeconds = 3600;
    cfg.wifiRetries = 10;

    cfg.ntpHost = "pool.ntp.org";
    cfg.ntpTimezone = "Europe/Dublin";

    // Leave the broker as XXXX and this block comes from the panel's own
    // store instead, which is what an image built by CI relies on.
    cfg.mqttEnabled = false;
    cfg.mqttBroker = "XXXX";
    cfg.mqttPort = 1883;
    cfg.mqttClientID = "my-display";
    cfg.mqttTopic = "mqtt/my-display";
    cfg.mqttRetries = 3;

    return cfg;
}
