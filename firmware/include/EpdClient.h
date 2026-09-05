#ifndef EPD_CLIENT_H
#define EPD_CLIENT_H

/**
  Everything a project needs from EpdClient, in one include.

      #include "EpdClient.h"

  The individual headers are still there and still work; this exists so a
  project's own files do not open with a column of them.

  Not included here, on purpose:

  - IBoard.h arrives with epd.h, which every project needs anyway.
  - MockBoard.h is for a project's host tests, not for the image it ships.
  - log_format.h, mem_utils.h, ota_offer.h and refresh_header.h are how the
    library is built rather than what it offers. Include one directly if you
    need it, and expect it to change without ceremony.
*/

#include "epd.h"           // epdBegin, epdBoard — call before anything else
#include "settings.h"      // ClientConfig, loadConfig

#include "wake.h"          // the steps of one wake
#include "network_utils.h" // configureWiFi, downloadFile, postJson
#include "image.h"         // draw a page, and cache the last one
#include "sleep_utils.h"   // sleep_for, sleep, deepSleep
#include "ota.h"           // take a firmware update, confirm it, roll it back
#include "sd_config.h"     // settings from a card, when USE_SDCARD is set

#include "backoff.h"       // how long to wait after a failure
#include "battery.h"       // volts to percent
#include "error_utils.h"   // esp_err_t values this library adds
#include "file_utils.h"    // write a downloaded page to the card
#include "log_utils.h"     // log, logf, and the MQTT relay
#include "time_utils.h"    // the clock, from NTP or the RTC
#include "user_agent.h"    // how this board introduces itself
#include "version.h"       // CLIENT_NAME, CLIENT_VERSION

#endif  // EPD_CLIENT_H
