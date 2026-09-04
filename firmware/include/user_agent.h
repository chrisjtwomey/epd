#ifndef __USER_AGENT_H__
#define __USER_AGENT_H__
#include <stddef.h>

/**
  Write "<name>/<version> (<device>)" into out, snprintf-style: out is
  always null-terminated when size > 0, and the return value is the length
  the full string needs. The comment is left out when device is null or
  empty.
*/
int buildUserAgent(char* out, size_t size, const char* name, const char* version,
                   const char* device);

/**
  The User-Agent this build sends: CLIENT_NAME/CLIENT_VERSION (device).
  Points at a static buffer that every call rewrites.
*/
const char* clientUserAgent(const char* device);

#endif // __USER_AGENT_H__
