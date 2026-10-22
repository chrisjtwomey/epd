#include "log_format.h"
#include "log_utils.h"
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <MqttLogger.h>

#include "log_backlog.h"

// The lines kept while the broker is unreachable: 30 hold a cold boot's lines
// before MQTT is up, and about 8 minutes of a board that logs 3-4 a minute.
// A product changes it with -DEPD_LOG_QUEUE_LINES=n; 0 keeps none.
#ifndef EPD_LOG_QUEUE_LINES
#define EPD_LOG_QUEUE_LINES 30
#endif
// Bytes per kept line: the prefix and about 150 characters, such as the
// Wi-Fi reconnect line with its reason, which is logged before MQTT is back.
static const size_t kQueueItemBytes = 200;

// The remote logger. static: a product's own global of the same name, such
// as WiFiClient client, must not clash with these at link time.
static WiFiClient espClient;
static PubSubClient client(espClient);
static MqttLogger mqttLogger(client, "", MqttLoggerMode::SerialOnly);
// Lines kept while the broker is unreachable, sent once it is back. The slots
// come from the heap on the first line: above 4 KB, a board with PSRAM puts
// them there.
static LogBacklog& backlog() {
    static char* slots =
        EPD_LOG_QUEUE_LINES ? (char*)malloc((size_t)EPD_LOG_QUEUE_LINES * kQueueItemBytes)
                            : nullptr;
    static LogBacklog kept(slots, EPD_LOG_QUEUE_LINES, kQueueItemBytes);
    return kept;
}
// The client ID configureMQTT was given, for keepMQTTConnected() to reconnect with.
static const char* mqttClientID = nullptr;
static uint32_t lastConnectAttemptMs = 0;
// A failed connect holds up the caller's loop, so the tries are spaced out.
static const uint32_t kReconnectMs = 30000;

esp_err_t configureMQTT(const char* broker, int port, const char* topic,
                        const char* clientID, int max_retries) {
    log(LOG_INFO, "configuring remote MQTT logging...");

    client.setServer(broker, port);
    // A whole line in one packet, with the header and the topic: PubSubClient's
    // 256 bytes would refuse a long line's pieces and pass on only its tail.
    const size_t packetBytes = MQTT_MAX_HEADER_SIZE + 2 + strlen(topic) + LOG_LINE_MAX;
    if (!client.setBufferSize((uint16_t)packetBytes))
        log(LOG_WARNING, "no memory for whole MQTT log lines; long lines arrive cut");
    mqttLogger.setTopic(topic);
    mqttClientID = clientID;
    // Attempt to connect to MQTT broker.
    int attempts = 0;
    while (attempts++ <= max_retries && !client.connect(clientID)) {
        logf(LOG_DEBUG, "connection attempt #%d...", attempts);
        delay(250);
    }
    lastConnectAttemptMs = millis();

    if (!client.connected()) {
        return ESP_ERR_TIMEOUT;
    }

    mqttLogger.setMode(MqttLoggerMode::MqttAndSerial);

    logf(LOG_INFO, "connected to MQTT broker %s:%d", broker, port);

    return ESP_OK;
}

void keepMQTTConnected() {
    if (!mqttClientID || client.loop()) return;

    uint32_t now = millis();
    if (now - lastConnectAttemptMs < kReconnectMs) return;
    lastConnectAttemptMs = now;
    if (!client.connect(mqttClientID)) return;

    mqttLogger.setMode(MqttLoggerMode::MqttAndSerial);
    // Also sends the lines queued while the connection was down.
    log(LOG_INFO, "reconnected to the MQTT broker");
}

static const char* levelName(uint16_t pri) {
    switch (pri) {
        case LOG_CRIT:    return "CRITICAL";
        case LOG_ERROR:   return "ERROR";
        case LOG_WARNING: return "WARNING";
        case LOG_NOTICE:  return "NOTICE";
        case LOG_DEBUG:   return "DEBUG";
        default:          return "INFO";
    }
}

static void writeLog(char* logMsg);

// A line's prefix, the local time and the level's name, written into out.
static const char* msgPrefix(uint16_t pri, char* out, size_t size) {
    formatPrefix(out, size, nowTzFmt().c_str(), levelName(pri));
    return out;
}

static uint16_t levelNow = LOG_LEVEL;

void setLogLevel(uint16_t level) { levelNow = level > LOG_LEVEL ? LOG_LEVEL : level; }

void log(uint16_t pri, const char* msg) { logf(pri, "%s", msg); }

void logf(uint16_t pri, const char* fmt, ...) {
    if (pri > levelNow) return;

    char line[LOG_LINE_MAX];
    char prefix[LOG_PREFIX_MAX];
    va_list args;
    va_start(args, fmt);
    formatLog(line, sizeof(line), msgPrefix(pri, prefix, sizeof(prefix)), fmt, args);
    va_end(args);
    writeLog(line);
}

// Write one line to the serial port and to the broker. While the broker is
// unreachable the line is also queued, cut to kQueueItemBytes, and the backlog
// goes out ahead of the next line once it reconnects.
static void writeLog(char* logMsg) {
    // MqttLogger sends, and prints, whatever fills its buffer as a line of its
    // own; one of LOG_LINE_MAX keeps every line whole, its line ending too.
    static bool lineBufferSized = false;
    if (!lineBufferSized) lineBufferSized = mqttLogger.setBufferSize(LOG_LINE_MAX);
    if (!client.connected()) {
        backlog().push(logMsg);
    } else if (backlog().count() > 0) {
        char kept[kQueueItemBytes];
        mqttLogger.setMode(MqttLoggerMode::MqttOnly);
        while (backlog().pop(kept, sizeof(kept))) mqttLogger.println(kept);
        mqttLogger.setMode(MqttLoggerMode::MqttAndSerial);
    }
    mqttLogger.println(logMsg);
}