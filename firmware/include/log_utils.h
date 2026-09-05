#ifndef __LOG_H__
#define __LOG_H__
#include "error_utils.h"
#include "time_utils.h"

// Enum of log verbosity levels.
#define LOG_CRIT 0
#define LOG_ERROR 1
#define LOG_WARNING 2
#define LOG_NOTICE 3
#define LOG_INFO 4
#define LOG_DEBUG 5
#ifndef LOG_LEVEL
// Debug logging by default.
#define LOG_LEVEL LOG_DEBUG
#endif

// log message entry history size
#define LOG_QUEUE_MAX_ENTRIES 10
// Bytes per queued entry. The queue copies exactly this many, so a line is
// staged through a buffer of this size and truncated to fit.
#define LOG_QUEUE_ITEM_MAX 100

/**
  Connect to a MQTT broker for remote logging.

  @param broker the hostname of the MQTT broker.
  @param port the port of the MQTT broker.
  @param topic the topic to publish logs to.
  @param clientID the name of the logger client to appear as.
  @param max_retries the number of connection attempts to make before fallback
  to serial-only logging.
  @returns the esp_err_t code:
  - ESP_OK if successful.
  - ESP_ERR_TIMEOUT if number of retries is exceeded without success.
*/
esp_err_t configureMQTT(const char* broker, int port, const char* topic,
                        const char* clientID, int max_retries);

/**
  Log a message.

  @param pri the log level / priority of the message, see LOG_LEVEL.
  @param msg the message to log.
*/
void log(uint16_t pri, const char* msg);

/**
  Log a message with formatting.

  @param pri the log level / priority of the message, see LOG_LEVEL.
  @param fmt the format of the log message
*/
void logf(uint16_t pri, const char* fmt, ...);

/**
  Converts a priority into a log level prefix.

  @param pri the log level / priority of the message, see LOG_LEVEL.
  @returns the string value of the priority.
*/
const char* msgPrefix(uint16_t pri);

/**
  Write one log line out, to the serial port and to the broker.

  While the broker is unreachable the line is also queued, and the backlog
  goes out ahead of the next line once it reconnects. A queued line is
  truncated to LOG_QUEUE_ITEM_MAX; one written straight out is not.

  @param msg the log message
*/
void writeLog(char* msg);
#endif