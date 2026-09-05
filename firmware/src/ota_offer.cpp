#include "ota_offer.h"

#include <string.h>

bool updateRefusedBefore(const char* offeredVersion, const char* rejectedVersion) {
    if (!offeredVersion || !offeredVersion[0]) return false;
    if (!rejectedVersion || !rejectedVersion[0]) return false;
    return strcmp(offeredVersion, rejectedVersion) == 0;
}

bool updateOffered(const char* runningVersion, const char* offeredVersion,
                   const char* offeredURL, const char* rejectedVersion) {
    if (!offeredURL || !offeredURL[0]) return false;
    if (!offeredVersion || !offeredVersion[0]) return false;
    if (updateRefusedBefore(offeredVersion, rejectedVersion)) return false;
    if (!runningVersion || !runningVersion[0]) return true;
    return strcmp(runningVersion, offeredVersion) != 0;
}
