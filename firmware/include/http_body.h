#ifndef EPD_HTTP_BODY_H
#define EPD_HTTP_BODY_H

#include <HTTPClient.h>

#include "body_read.h"

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
