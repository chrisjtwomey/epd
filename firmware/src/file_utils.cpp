#include "file_utils.h"

#if defined(USE_SDCARD)
#include "epd.h"
#include "log_utils.h"


esp_err_t writeFile(uint8_t* buf, size_t size, const char* filePath) {
    logf(LOG_DEBUG, "writing file to path %s", filePath);

    if (!epdBoard().sdWriteFile(filePath, buf, size)) {
        return ESP_ERR_EFILEW;
    }

    return ESP_OK;
}
#endif