#include "display_utils.h"
#include "IBoard.h"
#include <SPIFFS.h>

#include "log_utils.h"
#include "mem_utils.h"

// The board driver instance.
extern IBoard& board;

#define IMAGE_CACHE_PATH "/image.png"

bool startImageCache() {
    if (SPIFFS.begin(true)) return true;
    log(LOG_WARNING, "SPIFFS mount failed - image cache unavailable");
    return false;
}

bool saveImageCache(const uint8_t* buf, int32_t len) {
    File f = SPIFFS.open(IMAGE_CACHE_PATH, FILE_WRITE);
    if (!f) {
        log(LOG_WARNING, "saveImageCache: failed to open file");
        return false;
    }
    size_t written = f.write(buf, (size_t)len);
    f.close();
    return (int32_t)written == len;
}

bool loadImageCache() {
    File f = SPIFFS.open(IMAGE_CACHE_PATH, FILE_READ);
    if (!f || f.size() == 0) return false;
    int32_t len = (int32_t)f.size();
    uint8_t* buf = (uint8_t*)boardMalloc(len);
    if (!buf) { f.close(); return false; }
    f.read(buf, len);
    f.close();
    bool ok = board.drawPngFromBuffer(buf, len, 0, 0, false, true);
    free(buf);
    return ok;
}

esp_err_t loadImage(const char* filePath) {
    logf(LOG_INFO, "drawing image from path: %s", filePath);

    if (!board.drawPngFromSd(filePath, 0, 0, false, true)) {
        return ESP_ERR_EDRAW;
    }

    return ESP_OK;
}

esp_err_t loadImage(uint8_t* buf, int32_t len) {
    log(LOG_INFO, "drawing image from buffer");

    if (!board.drawPngFromBuffer(buf, len, 0, 0, false, true)) {
        return ESP_ERR_EDRAW;
    }

    return ESP_OK;
}
