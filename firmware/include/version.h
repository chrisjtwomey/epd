#ifndef __VERSION_H__
#define __VERSION_H__

/**
 * Client firmware version, reported in the boot log.
 *
 * The consuming project sets its own value in platformio.ini:
 *
 *     build_flags = -DCLIENT_VERSION='"v1.4.0"'
 *
 * so the library carries no project version of its own.
 */
#ifndef CLIENT_VERSION
#define CLIENT_VERSION "dev"
#endif

/**
 * Product token of the User-Agent the client sends, set the same way:
 *
 *     build_flags = -DCLIENT_NAME='"inkplate10-weather-cal"'
 *
 * The request then carries: inkplate10-weather-cal/v1.4.0 (Inkplate10).
 */
#ifndef CLIENT_NAME
#define CLIENT_NAME "EpdClient"
#endif

#endif // __VERSION_H__
