#include "user_agent.h"

#include <stdio.h>

#include "version.h"

int buildUserAgent(char* out, size_t size, const char* name, const char* version,
                   const char* device) {
    if (device && device[0])
        return snprintf(out, size, "%s/%s (%s)", name, version, device);
    return snprintf(out, size, "%s/%s", name, version);
}

const char* clientUserAgent(const char* device) {
    static char ua[96];
    buildUserAgent(ua, sizeof(ua), CLIENT_NAME, CLIENT_VERSION, device);
    return ua;
}
