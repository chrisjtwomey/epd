#include "log_format.h"
#include "log_utils.h"
#include <Arduino.h>
#include <WiFi.h>
#include <cppQueue.h>
#include <PubSubClient.h>
#include <MqttLogger.h>

// remote mqtt logger
WiFiClient espClient;
PubSubClient client(espClient);
MqttLogger mqttLogger(client, "", MqttLoggerMode::SerialOnly);
// queue to store messages to publish once mqtt connection is established.
cppQueue logQ(LOG_QUEUE_ITEM_MAX, LOG_QUEUE_MAX_ENTRIES, FIFO, true);
esp_err_t configureMQTT(const char* broker, int port, const char* topic,
                        const char* clientID, int max_retries) {
    log(LOG_INFO, "configuring remote MQTT logging...");

    client.setServer(broker, port);
    // Attempt to connect to MQTT broker.
    int attempts = 0;
    while (attempts++ <= max_retries && !client.connect(clientID)) {
        logf(LOG_DEBUG, "connection attempt #%d...", attempts);
        delay(250);
    }

    if (!client.connected()) {
        return ESP_ERR_TIMEOUT;
    }

    mqttLogger.setTopic(topic);
    mqttLogger.setMode(MqttLoggerMode::MqttAndSerial);

    logf(LOG_INFO, "connected to MQTT broker %s:%d", broker, port);

    return ESP_OK;
}

const char* msgPrefix(uint16_t pri) {
    char* priority;

    switch (pri) {
        case LOG_CRIT:
            priority = (char*)"CRITICAL";
            break;
        case LOG_ERROR:
            priority = (char*)"ERROR";
            break;
        case LOG_WARNING:
            priority = (char*)"WARNING";
            break;
        case LOG_NOTICE:
            priority = (char*)"NOTICE";
            break;
        case LOG_INFO:
            priority = (char*)"INFO";
            break;
        case LOG_DEBUG:
            priority = (char*)"DEBUG";
            break;
        default:
            priority = (char*)"INFO";
            break;
    }

    char* prefix = new char[35];
    String nowFmt = nowTzFmt();
    sprintf(prefix, "%s - %s - ", nowFmt.c_str(), priority);
    return prefix;
}

void log(uint16_t pri, const char* msg) {
    if (pri > LOG_LEVEL) return;

    const char* prefix = msgPrefix(pri);
    size_t prefixLen = strlen(prefix);
    size_t msgLen = strlen(msg);
    char buf[prefixLen + msgLen + 1];
    strcpy(buf, prefix);
    strcat(buf, msg);
    writeLog(buf);
}

void logf(uint16_t pri, const char* fmt, ...) {
    if (pri > LOG_LEVEL) return;

    char line[LOG_LINE_MAX];
    va_list args;
    va_start(args, fmt);
    formatLog(line, sizeof(line), msgPrefix(pri), fmt, args);
    va_end(args);
    writeLog(line);
}

void writeLog(char* logMsg) {
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