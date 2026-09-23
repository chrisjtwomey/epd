#ifndef EPD_LOG_FORMAT_H
#define EPD_LOG_FORMAT_H

#include <stdarg.h>
#include <stddef.h>

// The longest line the client logs. Anything longer is truncated.
#define LOG_LINE_MAX 512
// Room for a line's prefix: an RFC 3339 local time, the longest level name,
// CRITICAL, the two separators and the terminator come to 40.
#define LOG_PREFIX_MAX 48

/**
  Write a line's prefix, "<stamp> - <level> - ", into out.

  Always null-terminates, and never writes past size.

  @returns the length written, not counting the terminator.
*/
size_t formatPrefix(char* out, size_t size, const char* stamp, const char* level);

/**
  Write the prefix and then the formatted message into out.

  Always null-terminates, and never writes past size.

  @returns the length written, not counting the terminator.
*/
size_t formatLog(char* out, size_t size, const char* prefix, const char* fmt, va_list args);

#endif  // EPD_LOG_FORMAT_H