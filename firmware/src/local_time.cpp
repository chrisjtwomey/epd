#include "local_time.h"

#include <stdio.h>

size_t formatLocalTime(time_t t, char* out, size_t size) {
    if (!out || size == 0) return 0;

    struct tm local;
    char stamp[32];   // "2026-09-22T09:27:36+0100"
    if (!localtime_r(&t, &local) ||
        strftime(stamp, sizeof(stamp), "%Y-%m-%dT%H:%M:%S%z", &local) != 24) {
        out[0] = '\0';
        return 0;
    }

    int written = snprintf(out, size, "%.22s:%s", stamp, stamp + 22);
    if (written < 0) {
        out[0] = '\0';
        return 0;
    }
    return (size_t)written > size - 1 ? size - 1 : (size_t)written;
}
