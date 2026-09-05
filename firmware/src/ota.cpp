#include "ota.h"

#include <Arduino.h>
#include <HTTPUpdate.h>
#include <Update.h>
#include <WiFi.h>
#include <esp_ota_ops.h>

#include "log_utils.h"
#include "version.h"

// A slow link must not abort a megabyte mid-image; the default is 8 s.
#define OTA_HTTP_TIMEOUT_MS 20000

// The Arduino core confirms a pending image in initArduino(), before setup()
// ever runs, unless the application says it will judge the image itself. It
// asks through this weak symbol, so the trial lasts until otaConfirm().
extern "C" bool verifyRollbackLater() { return true; }

static void logProgress(int done, int total) {
    static int lastTenth = -1;
    if (total <= 0) return;
    int tenth = (int)((int64_t)done * 10 / total);
    if (tenth == lastTenth) return;
    lastTenth = tenth;
    logf(LOG_INFO, "firmware update %d%% (%d/%d bytes)", tenth * 10, done, total);
}

esp_err_t applyFirmwareUpdate(const char* url, const char* offeredVersion,
                              const char* userAgent) {
    logf(LOG_NOTICE, "firmware update offered: %s -> %s from %s", CLIENT_VERSION,
         offeredVersion, url);

    WiFiClient client;
    HTTPUpdate updater(OTA_HTTP_TIMEOUT_MS);
    updater.rebootOnUpdate(false);
    updater.setLedPin(-1);
    updater.onProgress(logProgress);

    // The running version goes out as x-ESP32-version, so a server that has
    // nothing newer answers 304 instead of sending the image again.
    t_httpUpdate_return result = updater.update(
        client, String(url), String(CLIENT_VERSION),
        [userAgent](HTTPClient* http) {
            if (userAgent && userAgent[0]) http->setUserAgent(userAgent);
        });

    switch (result) {
        case HTTP_UPDATE_OK:
            logf(LOG_NOTICE, "firmware %s written, restarting into it", offeredVersion);
            Serial.flush();
            ESP.restart();
            return ESP_OK;  // unreachable
        case HTTP_UPDATE_NO_UPDATES:
            log(LOG_WARNING, "server has nothing newer after all; keeping this image");
            return ESP_FAIL;
        default:
            logf(LOG_ERROR, "firmware update failed (%d): %s", updater.getLastError(),
                 updater.getLastErrorString().c_str());
            return ESP_FAIL;
    }
}

bool otaTrialPending() {
    const esp_partition_t* running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (!running || esp_ota_get_state_partition(running, &state) != ESP_OK) return false;
    return state == ESP_OTA_IMG_PENDING_VERIFY;
}

void otaConfirm() {
    if (!otaTrialPending()) return;
    if (esp_ota_mark_app_valid_cancel_rollback() == ESP_OK)
        logf(LOG_NOTICE, "firmware %s confirmed", CLIENT_VERSION);
    else
        log(LOG_ERROR, "failed to confirm the running firmware");
}

void otaRollback(const char* why) {
    logf(LOG_ERROR, "firmware %s failed its first cycle (%s); rolling back", CLIENT_VERSION,
         why ? why : "no reason given");
    Serial.flush();
    esp_ota_mark_app_invalid_rollback_and_reboot();
    // Only reached when the bootloader has no image to roll back to.
    log(LOG_ERROR, "no previous firmware to roll back to; restarting");
    Update.rollBack();
    ESP.restart();
}
