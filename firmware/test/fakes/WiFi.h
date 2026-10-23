// WiFi for the native_io tests: the link joins when the test says so, and
// the test raises the events the framework's event task would.
#ifndef EPD_FAKE_WIFI_H
#define EPD_FAKE_WIFI_H

#include <Arduino.h>

#include <functional>
#include <vector>

#include "HTTPClient.h"

#define WIFI_OFF 0
#define WIFI_STA 1

typedef enum { WL_IDLE_STATUS = 0, WL_CONNECTED = 3, WL_DISCONNECTED = 6 } wl_status_t;
typedef enum {
    ARDUINO_EVENT_WIFI_STA_DISCONNECTED = 5,
    ARDUINO_EVENT_WIFI_STA_GOT_IP = 7,
} arduino_event_id_t;
typedef arduino_event_id_t WiFiEvent_t;
typedef int wifi_err_reason_t;

struct WiFiEventInfo_t {
    struct {
        uint8_t reason;
    } wifi_sta_disconnected;
};

typedef void (*WiFiEventFuncCb)(WiFiEvent_t, WiFiEventInfo_t);

struct IPAddress {
    String toString() const { return String("192.168.1.50"); }
};

class WiFiClass {
public:
    // What a test reads back.
    int disconnectCount = 0;
    int beginCount = 0;
    int mode_ = WIFI_OFF;
    bool sleep_ = true;
    // What a test sets: the status the next check sees, and the join that
    // begin() starts: a join after this many ms of the fake clock, or none.
    wl_status_t status_ = WL_DISCONNECTED;
    long joinAfterMs = -1;

    void mode(int m) { mode_ = m; }
    void disconnect() {
        ++disconnectCount;
        status_ = WL_DISCONNECTED;
    }
    void begin(const char*, const char*) {
        ++beginCount;
        joinAt_ = joinAfterMs < 0 ? -1 : (long)(millis() + joinAfterMs);
    }
    wl_status_t status() {
        if (joinAt_ >= 0 && (long)millis() >= joinAt_) {
            joinAt_ = -1;
            status_ = WL_CONNECTED;
            raise(ARDUINO_EVENT_WIFI_STA_GOT_IP, 0);
        }
        return status_;
    }
    bool getSleep() { return sleep_; }
    void setSleep(bool on) { sleep_ = on; }
    IPAddress localIP() { return IPAddress(); }
    int8_t RSSI() { return -50; }
    const char* disconnectReasonName(wifi_err_reason_t r) {
        return r == 2 ? "AUTH_EXPIRE" : r == 201 ? "NO_AP_FOUND" : "UNSPECIFIED";
    }
    void onEvent(WiFiEventFuncCb cb, arduino_event_id_t id) { handlers_.push_back({id, cb}); }

    // The framework's event task, run by the test.
    void raise(arduino_event_id_t id, uint8_t reason) {
        WiFiEventInfo_t info = {};
        info.wifi_sta_disconnected.reason = reason;
        for (const auto& h : handlers_)
            if (h.id == id) h.cb(id, info);
    }
    void drop(uint8_t reason) {
        status_ = WL_DISCONNECTED;
        raise(ARDUINO_EVENT_WIFI_STA_DISCONNECTED, reason);
    }

private:
    struct Handler {
        arduino_event_id_t id;
        WiFiEventFuncCb cb;
    };
    std::vector<Handler> handlers_;
    long joinAt_ = -1;
};

extern WiFiClass WiFi;

#endif  // EPD_FAKE_WIFI_H
