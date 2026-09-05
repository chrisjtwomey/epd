#include "network_utils.h"

#include <HTTPClient.h>
#include <WiFi.h>

#include "log_utils.h"
#include "mem_utils.h"
#include "refresh_header.h"
esp_err_t configureWiFi(const char* ssid, const char* pass, int retries) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, pass);
    logf(LOG_INFO, "connecting to WiFi SSID %s...", ssid);

    // Retry until success or give up
    int attempts = 0;
    while (attempts++ <= retries && WiFi.status() != WL_CONNECTED) {
        logf(LOG_DEBUG, "connection attempt #%d...", attempts);
        delay(1000);
    }

    // If still not connected, error with timeout.
    if (WiFi.status() != WL_CONNECTED) {
        return ESP_ERR_TIMEOUT;
    }
    // Print the IP address
    logf(LOG_DEBUG, "IP address: %s", WiFi.localIP().toString());

    return ESP_OK;
}

// Copy a header value into a fixed field, logging what arrived.
static void copyHeader(HTTPClient& http, const char* name, char* out, size_t size) {
    if (!out || size == 0 || !http.hasHeader(name)) return;
    String value = http.header(name);
    strlcpy(out, value.c_str(), size);
    logf(LOG_INFO, "received header %s: %s", name, out);
}
uint8_t* downloadFile(const char* url, const char* userAgent, int32_t* defaultLen,
                      PageResponse* rsp) {
    logf(LOG_INFO, "downloading file at URL %s", url);

    bool sleep = WiFi.getSleep();
    WiFi.setSleep(false);

    HTTPClient http;

    const char* headersToCollect[] = {
        "X-Next-Refresh-Seconds",
        "X-Next-URL",
        "X-Firmware-Version",
        "X-Firmware-URL",
    };
    http.collectHeaders(headersToCollect,
                        sizeof(headersToCollect) / sizeof(headersToCollect[0]));

    if (userAgent && userAgent[0])
        http.setUserAgent(userAgent);

    // Connect with HTTP
    http.begin(url);

    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        if (httpCode < 0)
            logf(LOG_ERROR, "GET %s failed: %s", url, HTTPClient::errorToString(httpCode).c_str());
        else
            logf(LOG_ERROR, "Non-200 response from URL %s: %d", url, httpCode);
        http.end();
        WiFi.setSleep(sleep);
        return nullptr;
    }

    int32_t size = http.getSize();
    if (size == -1)
        size = *defaultLen;
    else
        *defaultLen = size;

    uint8_t* buffer = (uint8_t *)boardMalloc(size);
    if (!buffer) {
        logf(LOG_ERROR, "failed to allocate %d bytes for download buffer", size);
        http.end();
        WiFi.setSleep(sleep);
        return nullptr;
    }
    uint8_t *buffPtr = buffer;

    // The socket exists only after GET() has connected.
    http.getStream().setNoDelay(true);
    http.getStream().setTimeout(5);

    if (rsp) {
        if (http.hasHeader("X-Next-Refresh-Seconds")) {
            // Server is authoritative for *when* to refresh next; we just count
            // down. No timezone math on the client.
            String headerVal = http.header("X-Next-Refresh-Seconds");
            uint32_t parsed = 0;
            if (parseRefreshTime(headerVal.c_str(), &parsed)) {
                rsp->nextRefreshSeconds = parsed;
                logf(LOG_INFO, "received header X-Next-Refresh-Seconds: %u", parsed);
            } else {
                logf(LOG_WARNING, "X-Next-Refresh-Seconds value '%s' is malformed, ignoring",
                     headerVal.c_str());
            }
        } else {
            logf(LOG_WARNING, "header X-Next-Refresh-Seconds not found in response");
        }

        copyHeader(http, "X-Next-URL", rsp->nextURL, sizeof(rsp->nextURL));
        copyHeader(http, "X-Firmware-Version", rsp->firmwareVersion, sizeof(rsp->firmwareVersion));
        copyHeader(http, "X-Firmware-URL", rsp->firmwareURL, sizeof(rsp->firmwareURL));
    }

    int32_t total = http.getSize();
    int32_t len = total;

    uint8_t buff[512] = {0};

    WiFiClient* stream = http.getStreamPtr();
    while (http.connected() && (len > 0 || len == -1)) {
        size_t size = stream->available();

        if (size) {
            int c = stream->readBytes(
                buff, ((size > sizeof(buff)) ? sizeof(buff) : size));
            memcpy(buffPtr, buff, c);

            if (len > 0) len -= c;
            buffPtr += c;
        } else if (len == -1) {
            len = 0;
        }
    }

    http.end();
    WiFi.setSleep(sleep);

    return buffer;
}

int postJson(const char* url, const char* userAgent, const char* body) {
    HTTPClient http;
    if (userAgent && userAgent[0])
        http.setUserAgent(userAgent);
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST((uint8_t*)body, strlen(body));
    http.end();
    if (code < 0)
        logf(LOG_ERROR, "POST %s failed: %s", url, HTTPClient::errorToString(code).c_str());
    return code;
}
