#include <WiFi.h>

#include "log_utils.h"
#include "network_utils.h"
#include "wifi_retry.h"

// What configureWiFi was given, for keepWiFiConnected() to reconnect with.
static const char* wifiSSID = nullptr;
static const char* wifiPass = nullptr;
// A router takes a minute or two to restart; an attempt every 30 s finds it
// soon after without flooding it while it boots.
static WifiRetry wifiRetry(30000);
// Written by the Wi-Fi event task: why a working link dropped, for
// keepWiFiConnected(), and why the latest join failed, for configureWiFi().
static volatile uint8_t wifiLostReason = 0;
static volatile uint8_t wifiJoinReason = 0;

static void noteWifiLost(WiFiEvent_t, WiFiEventInfo_t info) {
    wifiJoinReason = info.wifi_sta_disconnected.reason;
    if (!wifiRetry.down()) wifiLostReason = info.wifi_sta_disconnected.reason;
}

esp_err_t configureWiFi(const char* ssid, const char* pass, int retries) {
    if (!wifiSSID) WiFi.onEvent(noteWifiLost, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
    wifiSSID = ssid;
    wifiPass = pass;
    WiFi.mode(WIFI_STA);
    // The framework keeps joining after a timeout, and a new config set while
    // it does is refused, so a retry would change nothing.
    WiFi.disconnect();
    wifiJoinReason = 0;
    WiFi.begin(ssid, pass);
    logf(LOG_INFO, "connecting to WiFi SSID %s...", ssid);

    const uint32_t startMs = millis();
    const uint32_t waitMs = (uint32_t)(retries + 1) * 1000;
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - startMs >= waitMs) {
            const uint8_t reason = wifiJoinReason;
            logf(LOG_WARNING, "wifi not joined in %lu ms; last reason %u (%s)",
                 (unsigned long)waitMs, (unsigned)reason,
                 WiFi.disconnectReasonName((wifi_err_reason_t)reason));
            return ESP_ERR_TIMEOUT;
        }
        delay(100);
    }
    logf(LOG_INFO, "wifi connected in %lu ms: %s", (unsigned long)(millis() - startMs),
         WiFi.localIP().toString().c_str());

    return ESP_OK;
}

void keepWiFiConnected() {
    if (!wifiSSID) return;
    const uint32_t nowMs = millis();
    const bool connected = WiFi.status() == WL_CONNECTED;
    const uint32_t downMs = wifiRetry.downForMs(nowMs);
    const bool wasDown = wifiRetry.down();
    if (wifiRetry.due(nowMs, connected)) {
        logf(LOG_WARNING, "wifi down for %lu s; connecting again", (unsigned long)(downMs / 1000));
        WiFi.disconnect();
        WiFi.begin(wifiSSID, wifiPass);
        return;
    }
    if (connected && wasDown) {
        const uint8_t reason = wifiLostReason;
        logf(LOG_NOTICE, "wifi back after %lu s: %s, %d dBm; lost with reason %u (%s)",
             (unsigned long)(downMs / 1000), WiFi.localIP().toString().c_str(), (int)WiFi.RSSI(),
             (unsigned)reason, WiFi.disconnectReasonName((wifi_err_reason_t)reason));
    }
}
