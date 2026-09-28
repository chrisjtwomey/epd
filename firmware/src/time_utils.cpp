#include "time_utils.h"

#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

#include "local_time.h"
#include "network_utils.h"

// Sized as PageResponse::serverTimezone, which holds only a whole zone.
static RTC_DATA_ATTR char savedZone[sizeof(PageResponse::serverTimezone)];

String nowTzFmt() { return timeTzFmt(time(nullptr)); }

String timeTzFmt(time_t t) {
    char out[LOCAL_TIME_MAX];
    formatLocalTime(t, out, sizeof(out));
    return String(out);
}

void setClock(time_t epoch) {
    const timeval now = {epoch, 0};
    settimeofday(&now, nullptr);
}

void setTimezone(const char* posixTz) {
    if (!posixTz || !posixTz[0]) return;
    strlcpy(savedZone, posixTz, sizeof(savedZone));
    restoreTimezone();
}

void restoreTimezone() {
    if (!savedZone[0]) return;
    setenv("TZ", savedZone, 1);
    tzset();
}
