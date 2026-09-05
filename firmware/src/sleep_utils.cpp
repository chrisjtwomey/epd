#include "sleep_utils.h"
#include "epd.h"
#include <WiFi.h>
#include <driver/rtc_io.h>
#include <ezTime.h>

#include "log_utils.h"


void sleep_for(uint32_t seconds) {
    time_t targetWakeTime = epdBoard().rtcGetEpoch() + (time_t)seconds;
    logf(LOG_DEBUG, "sleeping for %u seconds (RTC alarm at epoch %ld)",
         seconds, (long)targetWakeTime);
    sleep(targetWakeTime);
}

void sleep(time_t targetWakeTime) {
    log(LOG_DEBUG, "arming deep sleep RTC alarm wakeup");

    epdBoard().rtcSetAlarmEpoch(targetWakeTime);
    // The alarm pin and wake source are board-specific — the board owns them.
    epdBoard().enableWakeOnRtcAlarm();

    logf(LOG_DEBUG, "waking at %s", dateTime(targetWakeTime, RFC3339).c_str());

    deepSleep();
}

void deepSleep() {
    log(LOG_NOTICE, "deep sleeping now");
    WiFi.disconnect();
    WiFi.mode(WIFI_OFF);

#if defined(USE_SDCARD)
    epdBoard().sdCardSleep();
#endif

    esp_deep_sleep_start();
}