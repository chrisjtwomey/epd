#ifndef EPD_LOG_FORMAT_H
#define EPD_LOG_FORMAT_H

#include <stdarg.h>
#include <stddef.h>

// The longest line the client logs. Anything longer is truncated.
#define LOG_LINE_MAX 512

/**
  Write the prefix and then the formatted message into out.

  Always null-terminates, and never writes past size.

  @returns the length written, not counting the terminator.
*/
size_t formatLog(char* out, size_t size, const char* prefix, const char* fmt, va_list args);

#endif  // EPD_LOG_FORMAT_H