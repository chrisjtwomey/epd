#include "time_utils.h"
#include <Arduino.h>
#include <ezTime.h>

#include "IBoard.h"
#include "log_utils.h"

// The timezone store
Timezone myTz;

// The board driver instance.
extern IBoard& board;

/**
 * Return a RFC3339 formatted string of the current time.
 * 
 * @return String the RFC3339 formatted string of the current time.
 */
String nowTzFmt() {
    return myTz.dateTime(RFC3339);   // local time with its real offset, UTC until the zone is known
}

/**
  Connect to an NTP server and synchronize the on-board real-time clock.

  @param host the hostname of the NTP server (eg. pool.ntp.org).
  @param timezoneName the name of the timezone in Olson format (eg.
  Europe/Dublin)
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_ENTP if updating the NTP client fails.
*/
esp_err_t configureTime(const char* ntpHost, const char* timezoneName) {
    log(LOG_INFO, "configuring network time and RTC...");

    setServer(ntpHost);

    // One query, judged by its own result. waitForSync() would be satisfied
    // by the clock the RTC seeded at boot, synced or not.
    time_t t;
    unsigned long measuredAt;
    if (!queryNTP(String(ntpHost), t, measuredAt)) {
        logf(LOG_WARNING, "NTP query to %s failed: %s", ntpHost, errorString().c_str());
        return ESP_ERR_ENTP;
    }
    setTime(t);
    updateNTP();   // refines the clock and schedules the periodic re-sync events() runs

    if (!myTz.setLocation(F(timezoneName))) {
        logf(LOG_WARNING, "timezone lookup for %s failed: %s; times are shown in UTC",
             timezoneName, errorString().c_str());
    }

    // The RTC holds UTC. Local time is a display format, from myTz.
    board.rtcSetEpoch(now());
    logf(LOG_DEBUG, "RTC synced to %s", myTz.dateTime(RFC3339).c_str());

    return ESP_OK;
}

