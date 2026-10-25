#ifndef EPD_UTC_SCOPE_H
#define EPD_UTC_SCOPE_H

#include <stdlib.h>
#include <string.h>
#include <time.h>

/**
  Holds the process time zone at UTC while it is in scope, and puts the zone
  that was set back when it leaves.

  The Inkplate library turns an epoch into the RTC's clock fields, and back,
  with localtime() and mktime(), so the RTC keeps whatever zone is set. Read
  and written in UTC, it means the same moment after a reset, which forgets
  the zone, and across a change of the clocks.

  Pure: no hardware, no globals. Tested in test/test_inkplate/.
*/
class UtcScope {
public:
    UtcScope() {
        const char* zone = getenv("TZ");
        hadZone_ = zone != nullptr;
        if (hadZone_) {
            strncpy(zone_, zone, sizeof(zone_) - 1);
            zone_[sizeof(zone_) - 1] = '\0';
        }
        setenv("TZ", "UTC0", 1);
        tzset();
    }
    ~UtcScope() {
        if (hadZone_)
            setenv("TZ", zone_, 1);
        else
            unsetenv("TZ");
        tzset();
    }
    UtcScope(const UtcScope&) = delete;
    UtcScope& operator=(const UtcScope&) = delete;

private:
    char zone_[96] = "";
    bool hadZone_ = false;
};

#endif  // EPD_UTC_SCOPE_H
