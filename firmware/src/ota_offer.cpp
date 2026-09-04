#include "ota_offer.h"

#include <string.h>

bool updateOffered(const char* runningVersion, const char* offeredVersion,
                   const char* offeredURL) {
    if (!offeredURL || !offeredURL[0]) return false;
    if (!offeredVersion || !offeredVersion[0]) return false;
    if (!runningVersion || !runningVersion[0]) return true;
    return strcmp(runningVersion, offeredVersion) != 0;
}
