#include "file_utils.h"

#if defined(USE_SDCARD)
#include "IBoard.h"
#include "log_utils.h"

// The board driver instance.
extern IBoard& board;

/**
  Write a data buffer a file at a given path. Store the file on disk at a given path.

  @param buf the data buffer.
  @param size the size of the file to write.
  @param filePath the path of the file on disk.
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_EFILEW if number of retries is exceeded without success.
*/

esp_err_t writeFile(uint8_t* buf, size_t size, const char* filePath) {
    logf(LOG_DEBUG, "writing file to path %s", filePath);

    if (!board.sdWriteFile(filePath, buf, size)) {
        return ESP_ERR_EFILEW;
    }

    return ESP_OK;
}
#endif