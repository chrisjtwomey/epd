#include "network_utils.h"

#include <HTTPClient.h>
#include <WiFi.h>

#include "log_utils.h"
#include "mem_utils.h"
#include "refresh_header.h"
#include "version.h"
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

// The name a server answering the current contract uses, or the one it used
// before the prefix existed. Null when it sent neither.
static const char* present(HTTPClient& http, const char* name, const char* was) {
    if (http.hasHeader(name)) return name;
    if (was && http.hasHeader(was)) return was;
    return nullptr;
}

// Copy a header value into a fixed field, logging what arrived.
static void copyHeader(HTTPClient& http, const char* name, const char* was, char* out,
                       size_t size) {
    const char* found = out && size ? present(http, name, was) : nullptr;
    if (!found) return;
    String value = http.header(found);
    strlcpy(out, value.c_str(), size);
    logf(LOG_INFO, "received header %s: %s", found, out);
}

// Read a whole-number header into *out, leaving it alone when the header is
// absent or malformed.
static void numberHeader(HTTPClient& http, const char* name, const char* was, uint32_t* out) {
    const char* found = out ? present(http, name, was) : nullptr;
    if (!found) return;
    String value = http.header(found);
    uint32_t parsed = 0;
    if (parseRefreshTime(value.c_str(), &parsed)) {
        *out = parsed;
        logf(LOG_INFO, "received header %s: %u", found, parsed);
    } else {
        logf(LOG_WARNING, "%s value '%s' is malformed, ignoring", found, value.c_str());
    }
}

// What the server says about itself, on any response.
static void readServerHeaders(HTTPClient& http, PageResponse* rsp) {
    if (!rsp) return;
    copyHeader(http, EPD_H_SERVER_VERSION, EPD_H_WAS_SERVER_VERSION, rsp->serverVersion,
               sizeof(rsp->serverVersion));
    numberHeader(http, EPD_H_SERVER_EPOCH, nullptr, &rsp->serverEpoch);
    numberHeader(http, EPD_H_NEXT_SENSOR_POLL, nullptr, &rsp->nextSensorPollSeconds);
}

// The headers every request carries: the board decides these, not the
// User-Agent, so neither end has to parse an identity back out of a
// formatted string.
static void addDeviceHeaders(HTTPClient& http) {
    http.addHeader(EPD_H_DEVICE, CLIENT_NAME);
    http.addHeader(EPD_H_DEVICE_VERSION, CLIENT_VERSION);
}
uint8_t* downloadFile(const char* url, const char* userAgent, int32_t* defaultLen,
                      PageResponse* rsp) {
    logf(LOG_INFO, "downloading file at URL %s", url);

    bool sleep = WiFi.getSleep();
    WiFi.setSleep(false);

    HTTPClient http;

    const char* headersToCollect[] = {
        EPD_H_NEXT_REFRESH,     EPD_H_WAS_NEXT_REFRESH,
        EPD_H_NEXT_URL,         EPD_H_WAS_NEXT_URL,
        EPD_H_SERVER_VERSION,   EPD_H_WAS_SERVER_VERSION,
        EPD_H_SERVER_EPOCH,     EPD_H_NEXT_SENSOR_POLL,
        EPD_H_FIRMWARE_VERSION, EPD_H_WAS_FIRMWARE_VERSION,
        EPD_H_FIRMWARE_URL,     EPD_H_WAS_FIRMWARE_URL,
    };
    http.collectHeaders(headersToCollect,
                        sizeof(headersToCollect) / sizeof(headersToCollect[0]));

    if (userAgent && userAgent[0])
        http.setUserAgent(userAgent);

    // Connect with HTTP
    http.begin(url);
    addDeviceHeaders(http);

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
        // The server is authoritative for when to refresh next; the board just
        // counts down. No timezone arithmetic on the client.
        if (!present(http, EPD_H_NEXT_REFRESH, EPD_H_WAS_NEXT_REFRESH))
            logf(LOG_WARNING, "header %s not found in response", EPD_H_NEXT_REFRESH);
        numberHeader(http, EPD_H_NEXT_REFRESH, EPD_H_WAS_NEXT_REFRESH, &rsp->nextRefreshSeconds);

        copyHeader(http, EPD_H_NEXT_URL, EPD_H_WAS_NEXT_URL, rsp->nextURL, sizeof(rsp->nextURL));
        copyHeader(http, EPD_H_FIRMWARE_VERSION, EPD_H_WAS_FIRMWARE_VERSION, rsp->firmwareVersion,
                   sizeof(rsp->firmwareVersion));
        copyHeader(http, EPD_H_FIRMWARE_URL, EPD_H_WAS_FIRMWARE_URL, rsp->firmwareURL,
                   sizeof(rsp->firmwareURL));
        readServerHeaders(http, rsp);
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

int postJson(const char* url, const char* userAgent, const char* body, PageResponse* rsp) {
    HTTPClient http;
    const char* headersToCollect[] = {EPD_H_SERVER_VERSION, EPD_H_WAS_SERVER_VERSION,
                                      EPD_H_SERVER_EPOCH, EPD_H_NEXT_SENSOR_POLL};
    http.collectHeaders(headersToCollect, sizeof(headersToCollect) / sizeof(headersToCollect[0]));
    if (userAgent && userAgent[0])
        http.setUserAgent(userAgent);
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    addDeviceHeaders(http);
    int code = http.POST((uint8_t*)body, strlen(body));
    readServerHeaders(http, rsp);
    http.end();
    if (code < 0)
        logf(LOG_ERROR, "POST %s failed: %s", url, HTTPClient::errorToString(code).c_str());
    return code;
}
