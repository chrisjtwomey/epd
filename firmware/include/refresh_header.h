#ifndef EPD_REFRESH_HEADER_H
#define EPD_REFRESH_HEADER_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

/**
 * Parse a whole-number response header value into `*out`.
 *
 * The headers that carry a count of seconds send a non-negative integer and
 * nothing else. Returns true and writes the parsed value to `*out` on
 * success; returns false and leaves `*out` unchanged on parse failure (null
 * pointer, empty string, any non-digit character, or value > UINT32_MAX).
 */
bool parseRefreshTime(const char* headerVal, uint32_t* out);

/**
 * Copy a response header value into a fixed field of `size` bytes.
 *
 * A URL or a version cut short is wrong, so a value that does not fit is not
 * copied: returns false and leaves `out` unchanged.
 */
bool copyWholeValue(const char* headerVal, char* out, size_t size);

#endif
