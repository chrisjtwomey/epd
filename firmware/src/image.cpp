#include "image.h"
#include "epd.h"
#include <SPIFFS.h>

#include "log_utils.h"
#include "mem_utils.h"


#define IMAGE_CACHE_PATH "/image.png"
// A page is written here, and becomes the cache only once it is whole.
#define IMAGE_CACHE_WRITE_PATH "/image.tmp"

bool startImageCache() {
    if (SPIFFS.begin(true)) return true;
    log(LOG_WARNING, "SPIFFS mount failed - image cache unavailable");
    return false;
}

bool saveImageCache(const uint8_t* buf, int32_t len) {
    File f = SPIFFS.open(IMAGE_CACHE_WRITE_PATH, FILE_WRITE);
    if (!f) {
        log(LOG_WARNING, "saveImageCache: failed to open file");
        return false;
    }
    size_t written = f.write(buf, (size_t)len);
    f.close();
    // The decoder draws a cut PNG as if it were whole, so a short write must
    // not replace the last good page. SPIFFS will not rename over a file.
    if ((int32_t)written != len) {
        SPIFFS.remove(IMAGE_CACHE_WRITE_PATH);
        return false;
    }
    SPIFFS.remove(IMAGE_CACHE_PATH);
    return SPIFFS.rename(IMAGE_CACHE_WRITE_PATH, IMAGE_CACHE_PATH);
}

bool loadImageCache() {
    File f = SPIFFS.open(IMAGE_CACHE_PATH, FILE_READ);
    if (!f || f.size() == 0) return false;
    int32_t len = (int32_t)f.size();
    uint8_t* buf = (uint8_t*)boardMalloc(len);
    if (!buf) { f.close(); return false; }
    size_t got = f.read(buf, (size_t)len);
    f.close();
    if ((int32_t)got != len) {
        logf(LOG_WARNING, "cached page read short: %u of %ld bytes", (unsigned)got, (long)len);
        free(buf);
        return false;
    }
    bool ok = epdBoard().drawPngFromBuffer(buf, len, 0, 0, PngDraw::Invert);
    free(buf);
    return ok;
}

#if defined(USE_SDCARD)
esp_err_t loadImage(const char* filePath) {
    logf(LOG_INFO, "drawing image from path: %s", filePath);

    if (!epdBoard().drawPngFromSd(filePath, 0, 0, PngDraw::Invert)) {
        return ESP_ERR_EDRAW;
    }

    return ESP_OK;
}
#else
esp_err_t loadImage(const char* filePath) {
    logf(LOG_ERROR, "cannot draw %s: this build has no SD card support", filePath);
    return ESP_ERR_NOT_SUPPORTED;
}
#endif

esp_err_t loadImage(uint8_t* buf, int32_t len) {
    log(LOG_INFO, "drawing image from buffer");

    if (!epdBoard().drawPngFromBuffer(buf, len, 0, 0, PngDraw::Invert)) {
        return ESP_ERR_EDRAW;
    }

    return ESP_OK;
}
