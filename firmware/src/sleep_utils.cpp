#include "sleep_utils.h"
#include "IBoard.h"
#include <WiFi.h>
#include <driver/rtc_io.h>
#include <ezTime.h>

#include "log_utils.h"

// The board driver instance.
extern IBoard& board;

/**
  Enter deep sleep for `seconds` from now. The external RTC alarm fires
  exactly `seconds` later — no timezone math, no DST handling on the client.
*/
void sleep_for(uint32_t seconds) {
    time_t targetWakeTime = board.rtcGetEpoch() + (time_t)seconds;
    logf(LOG_DEBUG, "sleeping for %u seconds (RTC alarm at epoch %ld)",
         seconds, (long)targetWakeTime);
    sleep(targetWakeTime);
}

void sleep(time_t targetWakeTime) {
    log(LOG_DEBUG, "arming deep sleep RTC alarm wakeup");

    board.rtcSetAlarmEpoch(targetWakeTime);
    // The alarm pin and wake source are board-specific — the board owns them.
    board.enableWakeOnRtcAlarm();

    logf(LOG_DEBUG, "waking at %s", dateTime(targetWakeTime, RFC3339).c_str());

    deepSleep();
}

/**
  Enter deep sleep.
*/
void deepSleep() {
    log(LOG_NOTICE, "deep sleeping now");
    WiFi.disconnect();
    WiFi.mode(WIFI_OFF);

#if defined(USE_SDCARD)
    board.sdCardSleep();
#endif

    esp_deep_sleep_start();
}