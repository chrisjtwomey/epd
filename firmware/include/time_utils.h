#ifndef EPD_TIME_UTILS_H
#define EPD_TIME_UTILS_H
#include <Arduino.h>
#include <time.h>

#define SECONDS_IN_DAY 86400
#define SECONDS_IN_YEAR SECONDS_IN_DAY * 365

/** The time now as RFC 3339 local time; UTC until a time zone is set. */
String nowTzFmt();

/** t as RFC 3339 local time; UTC until a time zone is set. */
String timeTzFmt(time_t t);

/** Set the system clock to epoch, in UTC seconds. */
void setClock(time_t epoch);

/**
  Show local time in posixTz, a POSIX TZ string such as the server sends.

  The zone is kept in RTC memory, for restoreTimezone() after deep sleep. An
  empty or null string leaves the zone as it was.
*/
void setTimezone(const char* posixTz);

/** Show local time in the zone last set, once a wake from deep sleep has lost it. */
void restoreTimezone();
#endif
