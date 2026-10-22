#ifndef EPD_HTTP_REQUEST_H
#define EPD_HTTP_REQUEST_H

#include <HTTPClient.h>

#include "body_read.h"
#include "epd_headers.h"
#include "version.h"

/**
  Start a request with the headers every request carries. The board names
  itself in these, not in the User-Agent, so neither end has to parse an
  identity back out of a formatted string.

  @returns false when url cannot be read.
*/
inline bool beginRequest(HTTPClient& http, const char* url, const char* userAgent) {
    if (userAgent && userAgent[0]) http.setUserAgent(userAgent);
    if (!http.begin(url)) return false;
    http.addHeader(EPD_H_DEVICE, CLIENT_NAME);
    http.addHeader(EPD_H_DEVICE_VERSION, CLIENT_VERSION);
    return true;
}

/** A response body as HTTPClient receives it, for readBody and its kin. */
class HttpBody : public IBodySource {
public:
    explicit HttpBody(HTTPClient& http) : http_(http), stream_(*http.getStreamPtr()) {}
    size_t available() override { return stream_.available(); }
    size_t read(uint8_t* out, size_t len) override {
        const int n = stream_.read(out, len);
        return n > 0 ? (size_t)n : 0;
    }
    bool connected() override { return http_.connected(); }
    uint32_t nowMs() override { return millis(); }
    void wait() override { delay(1); }

private:
    HTTPClient& http_;
    WiFiClient& stream_;
};

#endif
