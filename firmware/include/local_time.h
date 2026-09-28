#ifndef EPD_LOCAL_TIME_H
#define EPD_LOCAL_TIME_H

#include <stddef.h>
#include <time.h>

// "2026-09-22T09:27:36+01:00" and its terminator.
#define LOCAL_TIME_MAX 26

/**
  Write t as RFC 3339 local time, in the zone TZ holds, into out.

  The offset has the colon RFC 3339 needs and strftime's %z leaves out.
  Always null-terminates, and never writes past size.

  @returns the length written, not counting the terminator.
*/
size_t formatLocalTime(time_t t, char* out, size_t size);

#endif  // EPD_LOCAL_TIME_H
