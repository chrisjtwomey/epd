#ifndef EPD_NETWORK_UTILS_H
#define EPD_NETWORK_UTILS_H
#include <stddef.h>
#include <stdint.h>

#include "epd_headers.h"
#include "error_utils.h"

/**
  What the server said alongside the image, from the response headers.

  A field the server did not send, or sent too long for the field, is left
  as the caller set it, so a zero value or an empty string means "not said
  this time".
*/
struct PageResponse {
    uint32_t nextRefreshSeconds;   // EPD_H_NEXT_REFRESH
    char nextURL[256];             // EPD_H_NEXT_URL
    char firmwareVersion[32];      // EPD_H_FIRMWARE_VERSION, when one is offered
    char firmwareURL[256];         // EPD_H_FIRMWARE_URL
    char serverVersion[32];        // EPD_H_SERVER_VERSION
    uint32_t serverEpoch;          // EPD_H_SERVER_EPOCH: UTC seconds when it answered
    char serverTimezone[64];       // EPD_H_SERVER_TIMEZONE: its zone, a POSIX TZ string
    uint32_t nextSensorPollSeconds;  // EPD_H_NEXT_SENSOR_POLL, from a server that sends one
};
/**
  Connect to a WiFi network in Station Mode.

  ssid and pass are kept, not copied, for keepWiFiConnected() to reconnect
  with. Both must outlive the connection, so pass static storage, never a
  local buffer.

  Each call starts a fresh join, ending any the framework still runs from the
  last one. A wait that ends without a connection logs the reason the join
  last failed.

  @param ssid the network SSID.
  @param pass the network password.
  @param retries how long to wait for the connection: one second, and one
  more for each retry.

  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_TIMEOUT if the wait ends without a connection.
*/
esp_err_t configureWiFi(const char* ssid, const char* pass, int retries);

/**
  Reconnect to Wi-Fi once the link drops, without blocking.

  The framework reconnects by itself only for some disconnect reasons, so an
  access point that restarts can leave a board off the network for good. A
  board that stays awake calls this on every pass of its loop; while the link
  is down it starts a new attempt every 30 s. Once the link is back it logs
  how long it was down and the reason it dropped. A board that sleeps after
  each wake does not need it.
*/
void keepWiFiConnected();

/**
  Download a file at the given URL into a buffer the caller frees.

  userAgent is sent as the User-Agent header; null or empty keeps the
  HTTP library's default.

  *size is the most to accept when the server sends no length, and is set to
  the length read. What the server said about the next wake and about
  firmware is written to rsp after any 200, even when the body then fails;
  pass nullptr to ignore it.

  Blocks until the body is read; a chunked body is joined. Fails when the
  server sends no byte for 5 s, closes before the body ends, sends more than
  the buffer holds, sends a chunk size that cannot be read, or sends an empty
  body.

  @returns the buffer, or nullptr when the request, the allocation or the
  read failed, or the body is empty.
*/
uint8_t* downloadFile(const char* url, const char* userAgent, int32_t* size,
                      PageResponse* rsp);

/**
  Download as downloadFile does, for an answer that changes the board, such
  as its settings. Once the board has a key, the answer must carry the
  server's signature over it under that key, or this returns nullptr.
*/
uint8_t* downloadSigned(const char* url, const char* userAgent, int32_t* size,
                        PageResponse* rsp);

/**
  POST body to url as application/json.

  What the server said about itself is written to rsp, which a POST fills
  only in part: a board that never fetches a page still learns the server's
  version and clock. Pass nullptr to ignore it.

  Once the board has a key, each post is signed with it. A 401 that asks
  for the server's clock sets the board's clock from it and posts once more.
  A 401 that asks the board to pair pairs it and posts once more, when the
  board has no key, or when the refusal is signed with the key it holds;
  otherwise the board keeps its key. The server refuses a post under a new
  key too until a person approves it, so the caller keeps the body for later
  on a 401.

  @returns the HTTP status code, or a negative HTTPClient error code when
  no response arrived.
*/
int postJson(const char* url, const char* userAgent, const char* body,
             PageResponse* rsp = nullptr);

#endif