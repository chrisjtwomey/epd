#ifndef EPD_IMAGE_H
#define EPD_IMAGE_H
#include "error_utils.h"

/**
  Load an image to the display buffer.

  @param filePath the path of the file on disk.
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_EDRAW if the image cannot be decoded.
*/
esp_err_t loadImage(const char* filePath);

/**
  Load a PNG image to the display buffer from a data buffer.

  @param buf the data buffer of png.
  @param len the size of buffer.
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_EDRAW if the image cannot be decoded.
*/
esp_err_t loadImage(uint8_t* buf, int32_t len);


/**
  Mount the filesystem the image cache lives on.

  Only worth calling on a board that redraws the last page — to put a banner
  over it, say. Nothing in this library needs it otherwise.

  @returns true when the cache is usable.
*/
bool startImageCache();

/**
  Save the raw PNG image bytes to SPIFFS, so the next boot can restore the
  image and draw over it rather than starting from a blank panel.

  @param buf  pointer to the PNG bytes.
  @param len  byte count.
  @returns true on success.
*/
bool saveImageCache(const uint8_t* buf, int32_t len);

/**
  Load the cached image PNG from SPIFFS into the display buffer.

  @returns true if the file existed and decoded successfully; false on any
  failure (first boot, SPIFFS not mounted, etc.) — the caller gracefully
  falls back to a white background.
*/
bool loadImageCache();
#endif