#ifndef EPD_IMAGE_H
#define EPD_IMAGE_H
#include "error_utils.h"

/**
  Draw a PNG from a file on the SD card into the frame buffer.

  @param filePath the path of the file on the SD card.
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_EDRAW if the image cannot be decoded.
  - ESP_ERR_NOT_SUPPORTED in a build without USE_SDCARD.
*/
esp_err_t drawImage(const char* filePath);

/**
  Draw a PNG from memory into the frame buffer.

  @param buf the data buffer of png.
  @param len the size of buffer.
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_EDRAW if the image cannot be decoded.
*/
esp_err_t drawImage(const uint8_t* buf, int32_t len);


/**
  Mount the filesystem the page cache lives on.

  Only worth calling on a board that redraws the last page — to put a banner
  over it, say. Nothing in this library needs it otherwise.

  The cache is LittleFS, on the partition named `spiffs`. LittleFS writes a
  whole page every time; SPIFFS reclaims at most 40 kB per write, so most
  page-sized writes failed once a few pages had gone through. A board that
  has no LittleFS there yet, an old SPIFFS cache included, has its partition
  formatted at the first mount: ESP-IDF logs the failed mount once, and the
  cached page is gone until the next save.

  @returns true when the cache is usable.
*/
bool startPageCache();

/**
  Save the page's PNG bytes to LittleFS, so a later boot can draw the page
  again, with a banner over it, rather than start from a blank panel.

  The page replaces the cache only when it was written whole: the decoder
  draws a cut PNG as if it were whole, so a failed save keeps the last good
  page.

  @param buf  pointer to the PNG bytes.
  @param len  byte count.
  @returns true on success.
*/
bool savePageCache(const uint8_t* buf, int32_t len);

/**
  Draw the cached page from LittleFS into the frame buffer.

  @returns true if the file existed and decoded successfully; false on any
  failure (first boot, LittleFS not mounted, etc.). After a decode that fails
  part way, the frame buffer holds part of the page.
*/
bool drawCachedPage();
#endif