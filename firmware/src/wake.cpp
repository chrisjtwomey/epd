#include "wake.h"

#include <Arduino.h>
#include <ezTime.h>

#include "IBoard.h"
#include "battery.h"
#include "display_utils.h"
#include "log_utils.h"
#include "ota.h"
#include "version.h"

// Provided by main.cpp (firmware) or test_main.cpp (tests).
extern IBoard& board;

void startBoard(uint8_t rotation) {
    Serial.begin(115200);
    board.begin();
    board.setRotation(rotation);
    board.rtcGetData();
    setTime(board.rtcGetEpoch());
}

void logWakeReason() {
    switch (esp_sleep_get_wakeup_cause()) {
        case ESP_SLEEP_WAKEUP_EXT0:
            log(LOG_DEBUG, "wakeup caused by external signal using RTC_IO.");
            board.rtcClearAlarmFlag();
            break;
        case ESP_SLEEP_WAKEUP_EXT1:
            log(LOG_DEBUG, "wakeup caused by external signal using RTC_CNTL.");
            break;
        case ESP_SLEEP_WAKEUP_TIMER:
            log(LOG_DEBUG, "wakeup caused by timer.");
            break;
        case ESP_SLEEP_WAKEUP_TOUCHPAD:
            log(LOG_DEBUG, "wakeup caused by touchpad.");
            break;
        case ESP_SLEEP_WAKEUP_ULP:
            log(LOG_DEBUG, "wakeup caused by ULP program.");
            break;
        default:
            log(LOG_DEBUG, "wakeup caused by RST pin or power button");
            break;
    }
}

int readBatteryPercent() {
    double volts = board.readBattery();
    logf(LOG_INFO, "battery voltage: %sv", String(volts, 2).c_str());
    int percent = getBatteryCapacity(volts);
    logf(LOG_INFO, "approx battery capacity: %d%%", percent);
    return percent;
}

esp_err_t connectNetwork(const ClientConfig& cfg) {
    if (configureWiFi(cfg.wifiSSID, cfg.wifiPass, cfg.wifiRetries) == ESP_ERR_TIMEOUT)
        return ESP_ERR_TIMEOUT;

    if (configureTime(cfg.ntpHost, cfg.ntpTimezone) != ESP_OK)
        log(LOG_WARNING, "failed to synchronize RTC with network time");

    if (cfg.mqttEnabled &&
        configureMQTT(cfg.mqttBroker, cfg.mqttPort, cfg.mqttTopic, cfg.mqttClientID,
                      cfg.mqttRetries) == ESP_ERR_TIMEOUT)
        log(LOG_WARNING, "failed to connect remote logging, fallback to serial");

    return ESP_OK;
}

bool fetchPage(const char* url, const char* userAgent, int retries, PageFetch* out,
               const char** errMsg) {
    for (int attempt = 0; attempt <= retries; ++attempt) {
        logf(LOG_DEBUG, "image download attempt #%d", attempt + 1);
        out->data = downloadFile(url, userAgent, &out->length, &out->response);
        if (out->data) return true;
    }
    *errMsg = "file download error";
    log(LOG_ERROR, *errMsg);
    return false;
}

bool drawPage(const PageFetch& page, const char* filePath, int retries,
              const std::function<void()>& overlay, const char** errMsg) {
    for (int attempt = 0; attempt <= retries; ++attempt) {
        logf(LOG_DEBUG, "image draw attempt #%d", attempt + 1);

        board.clearDisplay();
        if ((filePath ? loadImage(filePath) : loadImage(page.data, page.length)) != ESP_OK)
            continue;

        if (overlay) overlay();
        board.display();
        return true;
    }
    *errMsg = "image load error";
    log(LOG_ERROR, *errMsg);
    return false;
}

void takeOfferedUpdate(const PageResponse& rsp, const char* userAgent, int batteryPercent,
                       int minBatteryPercent) {
    const char* rejected = otaRejectedVersion();

    if (updateRefusedBefore(rsp.firmwareVersion, rejected)) {
        logf(LOG_WARNING, "firmware %s is offered again; this board rolled back from it",
             rsp.firmwareVersion);
        return;
    }
    if (!updateOffered(CLIENT_VERSION, rsp.firmwareVersion, rsp.firmwareURL, rejected)) return;

    if (batteryPercent < minBatteryPercent) {
        logf(LOG_NOTICE, "firmware %s offered but battery is %d%%; waiting", rsp.firmwareVersion,
             batteryPercent);
        return;
    }
    applyFirmwareUpdate(rsp.firmwareURL, rsp.firmwareVersion, userAgent);
}
