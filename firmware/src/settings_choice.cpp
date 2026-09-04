#include "settings.h"

#include <string.h>

bool isPlaceholder(const char* value) {
    if (!value || !value[0]) return true;
    if (strcmp(value, "XXXX") == 0) return true;
    return strstr(value, "YOUR_") != nullptr;
}

const char* chooseSetting(const char* compiled, const char* stored) {
    if (!isPlaceholder(compiled)) return compiled;
    if (!isPlaceholder(stored)) return stored;
    return compiled;
}
