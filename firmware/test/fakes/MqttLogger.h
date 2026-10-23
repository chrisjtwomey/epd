// MqttLogger for the native_io tests: keeps what reached the broker and what
// reached the serial port, line by line.
#ifndef EPD_FAKE_MQTTLOGGER_H
#define EPD_FAKE_MQTTLOGGER_H

#include <string>
#include <vector>

#include "PubSubClient.h"

enum class MqttLoggerMode { MqttAndSerial = 0, MqttOnly = 1, SerialOnly = 2 };

namespace fake {
struct Lines {
    std::vector<std::string> broker, serial;
    std::string topic;
    void clear() {
        broker.clear();
        serial.clear();
    }
};
inline Lines& lines() {
    static Lines l;
    return l;
}
}  // namespace fake

class MqttLogger {
public:
    MqttLogger(PubSubClient& client, const char* topic, MqttLoggerMode mode)
        : client_(client), mode_(mode) {
        fake::lines().topic = topic;
    }
    void setTopic(const char* topic) { fake::lines().topic = topic; }
    void setMode(MqttLoggerMode mode) { mode_ = mode; }
    bool setBufferSize(uint16_t) { return true; }
    size_t println(const char* line) {
        if (mode_ != MqttLoggerMode::SerialOnly && client_.connected())
            fake::lines().broker.push_back(line);
        if (mode_ != MqttLoggerMode::MqttOnly) fake::lines().serial.push_back(line);
        return strlen(line);
    }

private:
    PubSubClient& client_;
    MqttLoggerMode mode_;
};

#endif  // EPD_FAKE_MQTTLOGGER_H
