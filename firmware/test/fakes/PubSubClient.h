// PubSubClient for the native_io tests: the broker is up or down as the test
// says, and every connect is counted.
#ifndef EPD_FAKE_PUBSUBCLIENT_H
#define EPD_FAKE_PUBSUBCLIENT_H

#include <Arduino.h>

#include <string>

#include "HTTPClient.h"

#define MQTT_MAX_HEADER_SIZE 5

namespace fake {
struct Broker {
    bool up = true;
    bool bufferOk = true;
    int connects = 0;
    uint16_t bufferSize = 0;
    std::string server, clientID;
    int port = 0;
};
inline Broker& broker() {
    static Broker b;
    return b;
}
}  // namespace fake

class PubSubClient {
public:
    explicit PubSubClient(WiFiClient&) {}
    PubSubClient& setServer(const char* host, uint16_t port) {
        fake::broker().server = host;
        fake::broker().port = port;
        return *this;
    }
    bool setBufferSize(uint16_t size) {
        if (!fake::broker().bufferOk) return false;
        fake::broker().bufferSize = size;
        return true;
    }
    bool connect(const char* id) {
        ++fake::broker().connects;
        fake::broker().clientID = id;
        connected_ = fake::broker().up;
        return connected_;
    }
    bool connected() {
        if (!fake::broker().up) connected_ = false;
        return connected_;
    }
    bool loop() { return connected(); }

private:
    bool connected_ = false;
};

#endif  // EPD_FAKE_PUBSUBCLIENT_H
