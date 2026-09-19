#include "version_compat.h"

#include <ctype.h>
#include <stdlib.h>

// The major and minor of a version, or false when s is not one.
static bool readVersion(const char* s, long* major, long* minor) {
    if (!s) return false;
    if (*s == 'v' || *s == 'V') ++s;
    long parts[3];
    for (int i = 0; i < 3; ++i) {
        if (!isdigit((unsigned char)*s)) return false;
        char* end;
        parts[i] = strtol(s, &end, 10);
        s = end;
        if (i < 2) {
            if (*s != '.') return false;
            ++s;
        }
    }
    // After the patch number, only what git describe or semver can add.
    if (*s != '\0' && *s != '-' && *s != '+') return false;
    *major = parts[0];
    *minor = parts[1];
    return true;
}

VersionMatch versionsMatch(const char* a, const char* b) {
    long aMajor, aMinor, bMajor, bMinor;
    if (!readVersion(a, &aMajor, &aMinor) || !readVersion(b, &bMajor, &bMinor))
        return VERSIONS_UNKNOWN;
    if (aMajor != bMajor) return VERSIONS_DIFFER;
    if (aMajor == 0 && aMinor != bMinor) return VERSIONS_DIFFER;
    return VERSIONS_MATCH;
}
