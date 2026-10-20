#include "ota.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <Update.h>
#include <WiFi.h>
#include <esp_ota_ops.h>
#include <mbedtls/md.h>

#include <Preferences.h>

#include "board_key.h"
#include "current_board_key.h"
#include "epd_headers.h"
#include "log_utils.h"
#include "network_utils.h"
#include "version.h"

// A slow link must not abort a megabyte mid-image; HTTPClient's default is 5 s.
#define OTA_HTTP_TIMEOUT_MS 20000

// Where the client keeps what it learned about images, beside its settings.
#define OTA_NAMESPACE "epd"
#define OTA_REJECTED_KEY "ota_rejected"

// The Arduino core confirms a pending image in initArduino(), before setup()
// ever runs, unless the application says it will judge the image itself. It
// asks through this weak symbol, so the trial lasts until otaConfirm().
extern "C" bool verifyRollbackLater() { return true; }

static OtaProgress progressHook = nullptr;

static void logProgress(int done, int total) {
    static int lastTenth = -1;
    if (progressHook) progressHook(done, total);
    if (total <= 0) return;
    int tenth = (int)((int64_t)done * 10 / total);
    if (tenth == lastTenth) return;
    lastTenth = tenth;
    logf(LOG_INFO, "firmware update %d%% (%d/%d bytes)", tenth * 10, done, total);
}

// The image as it arrives: written to the idle slot and hashed together.
struct Download {
    int done;
    int total;
    uint8_t sha256[32];
};

static bool receive(HTTPClient& http, Download* d) {
    mbedtls_md_context_t sha;
    mbedtls_md_init(&sha);
    mbedtls_md_setup(&sha, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 0);
    mbedtls_md_starts(&sha);
    WiFiClient* stream = http.getStreamPtr();
    static uint8_t buf[2048];
    uint32_t lastDataMs = millis();
    bool written = true;
    while (d->done < d->total) {
        const size_t ready = stream->available();
        if (!ready) {
            if (!http.connected() || millis() - lastDataMs > OTA_HTTP_TIMEOUT_MS) break;
            delay(1);
            continue;
        }
        const size_t want = ready < sizeof(buf) ? ready : sizeof(buf);
        const int got = stream->readBytes(buf, want);
        if (got <= 0) continue;
        lastDataMs = millis();
        if (Update.write(buf, (size_t)got) != (size_t)got) {
            written = false;
            break;
        }
        mbedtls_md_update(&sha, buf, (size_t)got);
        d->done += got;
        logProgress(d->done, d->total);
    }
    mbedtls_md_finish(&sha, d->sha256);
    mbedtls_md_free(&sha);
    return written && d->done == d->total;
}

esp_err_t applyFirmwareUpdate(const char* url, const char* offeredVersion,
                              const char* userAgent, OtaProgress onProgress) {
    progressHook = onProgress;
    logf(LOG_NOTICE, "firmware update offered: %s -> %s from %s", CLIENT_VERSION,
         offeredVersion, url);

    HTTPClient http;
    const char* headers[] = {"x-MD5", CONTENT_DIGEST_HEADER, SIGNATURE_INPUT_HEADER,
                             SIGNATURE_HEADER};
    http.collectHeaders(headers, sizeof(headers) / sizeof(headers[0]));
    http.setTimeout(OTA_HTTP_TIMEOUT_MS);
    if (userAgent && userAgent[0]) http.setUserAgent(userAgent);
    if (!http.begin(url)) {
        logf(LOG_ERROR, "firmware update failed: %s is not a URL", url);
        return ESP_FAIL;
    }
    // The device and the key id name the key the server signs the image
    // with. The running version lets a server with nothing newer answer 304
    // instead of sending the image again.
    http.addHeader(EPD_H_DEVICE, CLIENT_NAME);
    http.addHeader(EPD_H_DEVICE_VERSION, CLIENT_VERSION);
    if (currentBoardKey().present) http.addHeader(EPD_H_KEY_ID, currentBoardKey().id);
    http.addHeader("x-ESP32-version", CLIENT_VERSION);
    const int code = http.GET();
    if (code == HTTP_CODE_NOT_MODIFIED) {
        http.end();
        log(LOG_WARNING, "server has nothing newer after all; keeping this image");
        return ESP_FAIL;
    }
    Download d = {0, http.getSize(), {0}};
    if (code != HTTP_CODE_OK || d.total <= 0) {
        logf(LOG_ERROR, "firmware update failed: %s answered %d, length %d", url, code, d.total);
        http.end();
        return ESP_FAIL;
    }
    if (!Update.begin((size_t)d.total, U_FLASH)) {
        logf(LOG_ERROR, "firmware update failed: %s", Update.errorString());
        http.end();
        return ESP_FAIL;
    }
    const String md5 = http.header("x-MD5");
    if (md5.length() == 32) Update.setMD5(md5.c_str());
    const String digest = http.header(CONTENT_DIGEST_HEADER);
    const String input = http.header(SIGNATURE_INPUT_HEADER);
    const String signature = http.header(SIGNATURE_HEADER);
    const bool whole = receive(http, &d);
    http.end();
    if (!whole) {
        Update.abort();
        logf(LOG_ERROR, "firmware update failed after %d of %d bytes", d.done, d.total);
        return ESP_FAIL;
    }

    const BoardKey& key = currentBoardKey();
    char why[112];
    if (key.present && !answerHolds(key, code, d.sha256, "GET", url, digest.c_str(),
                                    input.c_str(), signature.c_str(), (uint32_t)time(nullptr),
                                    why, sizeof(why))) {
        Update.abort();
        logf(LOG_ERROR, "firmware %s refused: %s", offeredVersion, why);
        return ESP_FAIL;
    }
    // end() checks the MD5, then makes the new image the one to boot.
    if (!Update.end()) {
        logf(LOG_ERROR, "firmware update failed: %s", Update.errorString());
        return ESP_FAIL;
    }
    logf(LOG_NOTICE, "firmware %s written, restarting into it", offeredVersion);
    Serial.flush();
    ESP.restart();
    return ESP_OK;  // unreachable
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

const char* otaRejectedVersion() {
    static String rejected;
    Preferences prefs;
    if (!prefs.begin(OTA_NAMESPACE, true)) return "";
    // isKey() first: getString() on an absent key logs an error of its own.
    rejected = prefs.isKey(OTA_REJECTED_KEY) ? prefs.getString(OTA_REJECTED_KEY, "") : String("");
    prefs.end();
    return rejected.c_str();
}

static void rememberRejected(const char* version) {
    Preferences prefs;
    if (!prefs.begin(OTA_NAMESPACE, false)) return;
    prefs.putString(OTA_REJECTED_KEY, version);
    prefs.end();
}

void otaRollback(const char* why) {
    logf(LOG_ERROR, "firmware %s failed its first cycle (%s); rolling back", CLIENT_VERSION,
         why ? why : "no reason given");
    // Recorded before the reboot, so the same image is refused next time.
    rememberRejected(CLIENT_VERSION);
    Serial.flush();
    esp_ota_mark_app_invalid_rollback_and_reboot();
    // Only reached when the bootloader has no image to roll back to.
    log(LOG_ERROR, "no previous firmware to roll back to; restarting");
    Update.rollBack();
    ESP.restart();
}

