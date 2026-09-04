#ifndef __OTA_H__
#define __OTA_H__

#include "error_utils.h"
#include "ota_offer.h"

/**
  Fetch the image at url and write it to the idle app slot, then restart.

  Returns only when the update did not happen, so the caller carries on with
  the wake it was in the middle of and tries again at the next one.

  @param url where to fetch the image.
  @param offeredVersion the version the server offered, for the log.
  @param userAgent the User-Agent to send, so the server knows who asked.
  @returns ESP_OK never (the board restarts), ESP_FAIL on any failure.
*/
esp_err_t applyFirmwareUpdate(const char* url, const char* offeredVersion,
                              const char* userAgent);

/**
  Whether this is the first boot of a freshly written image.

  The bootloader marks a new image as pending until the application says it
  works. An image that reboots or sleeps while still pending is rolled back,
  so every path out of a trial boot must call otaConfirm() or otaRollback().
*/
bool otaTrialPending();

/** Keep the running image. Does nothing when this is not a trial boot. */
void otaConfirm();

/** Give up on the running image and boot the previous one. Does not return. */
void otaRollback(const char* why);

#endif  // __OTA_H__
