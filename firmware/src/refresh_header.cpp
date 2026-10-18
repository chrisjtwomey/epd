#include "refresh_header.h"

#include <string.h>

bool parseRefreshTime(const char* headerVal, uint32_t* out) {
    if (!headerVal || !out || *headerVal == '\0') return false;

    uint64_t acc = 0;
    for (const char* p = headerVal; *p; ++p) {
        if (*p < '0' || *p > '9') return false;
        acc = acc * 10 + (uint64_t)(*p - '0');
        if (acc > UINT32_MAX) return false;
    }
    *out = (uint32_t)acc;
    return true;
}

bool copyWholeValue(const char* headerVal, char* out, size_t size) {
    if (!headerVal || !out || !size) return false;
    const size_t len = strlen(headerVal);
    if (len >= size) return false;
    memcpy(out, headerVal, len + 1);
    return true;
}
