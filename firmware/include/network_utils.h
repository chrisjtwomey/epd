#ifndef __NETWORK_H__
#define __NETWORK_H__
#include <stddef.h>
#include <stdint.h>

#include "error_utils.h"

/**
  What the server said alongside the image, from the response headers.

  A field the server did not send is left as the caller set it, so a zero
  value or an empty string means "not said this time".
*/
struct PageResponse {
    uint32_t nextRefreshSeconds;   // X-Next-Refresh-Seconds
    char nextURL[256];             // X-Next-URL
    char firmwareVersion[32];      // X-Server-Firmware-Version, when one is offered
    char firmwareURL[256];         // X-Server-Firmware-URL
};
/**
  Connect to a WiFi network in Station Mode.

  @param ssid the network SSID.
  @param pass the network password.
  @param retries the number of connection attempts to make before returning an
  error.
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_TIMEOUT if number of retries is exceeded without success.
*/
esp_err_t configureWiFi(const char* ssid, const char* pass, int retries);

/**
  Download a file at the given URL into a buffer the caller frees.

  userAgent is sent as the User-Agent header; null or empty keeps the
  HTTP library's default.

  *size is the expected length, used when the server sends none, and is set
  to the length the server reported. What the server said about the next
  wake and about firmware is written to rsp; pass nullptr to ignore it.

  @returns the buffer, or nullptr when the request or the allocation failed.
*/
uint8_t* downloadFile(const char* url, const char* userAgent, int32_t* size,
                      PageResponse* rsp);

/**
  POST body to url as application/json.

  @returns the HTTP status code, or a negative HTTPClient error code when
  no response arrived.
*/
int postJson(const char* url, const char* userAgent, const char* body);
#endif