#include "log_format.h"
#include "log_utils.h"
#include <Arduino.h>
#include <WiFi.h>
#include <cppQueue.h>
#include <PubSubClient.h>
#include <MqttLogger.h>

// The remote logger. static: a product's own global of the same name, such
// as WiFiClient client, must not clash with these at link time.
static WiFiClient espClient;
static PubSubClient client(espClient);
static MqttLogger mqttLogger(client, "", MqttLoggerMode::SerialOnly);
// Lines kept while the broker is unreachable, sent once it is back.
static cppQueue logQ(LOG_QUEUE_ITEM_MAX, LOG_QUEUE_MAX_ENTRIES, FIFO, true);
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

const char* msgPrefix(uint16_t pri, char* out, size_t size) {
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

void writeLog(char* logMsg) {
    // MqttLogger sends, and prints, whatever fills its buffer as a line of its
    // own; one of LOG_LINE_MAX keeps every line whole, its line ending too.
    static bool lineBufferSized = false;
    if (!lineBufferSized) lineBufferSized = mqttLogger.setBufferSize(LOG_LINE_MAX);
    if (!client.connected()) {
        // Stage the line: push copies a whole record out of whatever it is
        // given, so a shorter buffer would be read past its end, and a longer
        // one would be stored without a terminator.
        char slot[LOG_QUEUE_ITEM_MAX];
        strlcpy(slot, logMsg, sizeof(slot));
        logQ.push(slot);
    } else {
        // Pop into a buffer of its own: pop copies into whatever pointer it
        // is given, and logMsg is still the line about to be written.
        if (logQ.getCount() > 0) {
            char queuedMsg[LOG_QUEUE_ITEM_MAX];
            mqttLogger.setMode(MqttLoggerMode::MqttOnly);
            while (!logQ.isEmpty()) {
                logQ.pop(queuedMsg);
                mqttLogger.println(queuedMsg);
            }
            mqttLogger.setMode(MqttLoggerMode::MqttAndSerial);
        }
    }
    // print/send the current log (logMsg is unaffected by the flush above)
    mqttLogger.println(logMsg);
}