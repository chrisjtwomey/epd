#ifndef __WAKE_H__
#define __WAKE_H__

#include <stdint.h>

#include <functional>

#include "error_utils.h"
#include "network_utils.h"
#include "settings.h"

/**
  The steps of one wake.

  Each is built from the library's own calls and holds no policy: how many
  times to try and what a flat battery means are the caller's to decide. The
  order of the steps, and how a wake ends, is in app.cpp for a board that
  sleeps, and in the project's own loop for a board that does not.
*/

/**
  Bring the board up: serial, panel, rotation, and the clock from the RTC.

  The banner is left to the caller, which knows what to say. So is the image
  cache, which costs a filesystem and only earns it on a board that draws
  banners over the last page.
*/
void startBoard(uint8_t rotation);

/** Log why the board woke, and clear the RTC alarm when that was the cause. */
void logWakeReason();

/** Read the battery, and log both the voltage and what it means. */
int readBatteryPercent();

/**
  Connect to the network, set the clock from NTP, and start remote logging.

  Only WiFi is worth giving up for. A clock left on the RTC, or a broker that
  will not answer, are warnings: the panel can still be drawn.

  @returns ESP_OK, or ESP_ERR_TIMEOUT when WiFi did not connect.
*/
esp_err_t connectNetwork(const ClientConfig& cfg);

/** One page, downloaded. ``data`` is the caller's to free. */
struct PageFetch {
    uint8_t* data;
    int32_t length;
    PageResponse response;
};

/**
  Download a page, trying again up to ``retries`` further times.

  @param out on entry, ``length`` is the size to expect when the server sends
  no Content-Length; on success, the buffer and what the server said.
  @param errMsg set to what to put on the panel when this returns false.
  @returns true when a page was downloaded.
*/
bool fetchPage(const char* url, const char* userAgent, int retries, PageFetch* out,
               const char** errMsg);

/**
  Draw a page, trying again up to ``retries`` further times.

  @param filePath a copy on disk to draw from; null draws from the buffer.
  @param overlay drawn over the page before the panel is refreshed, which is
  the only moment it can be; empty to draw the page alone. A board that draws
  nothing over its pages keeps the indicator's fonts out of its image.
  @param errMsg set to what to put on the panel when this returns false.
  @returns true when the page reached the panel.
*/
bool drawPage(const PageFetch& page, const char* filePath, int retries,
              const std::function<void()>& overlay, const char** errMsg);

/**
  Take the update the page response offered, when there is one to take.

  Says why it did not, when it did not. Returns only when nothing was
  flashed, since a flashed image restarts the board.

  @param minBatteryPercent below which an update waits for a charge; 0 for a
  board on mains power.
*/
void takeOfferedUpdate(const PageResponse& rsp, const char* userAgent, int batteryPercent,
                       int minBatteryPercent);

#endif  // __WAKE_H__
