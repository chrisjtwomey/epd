#include "log_format.h"

#include <stdio.h>
#include <string.h>

size_t formatLog(char* out, size_t size, const char* prefix, const char* fmt, va_list args) {
    if (!out || size == 0) return 0;

    size_t written = 0;
    if (prefix && prefix[0]) {
        written = strlen(prefix);
        if (written > size - 1) written = size - 1;
        memcpy(out, prefix, written);
    }
    out[written] = '\0';

    if (!fmt || written + 1 >= size) return written;

    int formatted = vsnprintf(out + written, size - written, fmt, args);
    if (formatted < 0) return written;

    written += (size_t)formatted;
    return written > size - 1 ? size - 1 : written;
}
