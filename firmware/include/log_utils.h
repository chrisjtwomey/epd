#ifndef EPD_LOG_UTILS_H
#define EPD_LOG_UTILS_H
#include "error_utils.h"
#include "log_format.h"
#include "time_utils.h"

// Enum of log verbosity levels.
#define LOG_CRIT 0
#define LOG_ERROR 1
#define LOG_WARNING 2
#define LOG_NOTICE 3
#define LOG_INFO 4
#define LOG_DEBUG 5
#ifndef LOG_LEVEL
// The most a build logs, and the level it starts at: debug by default.
#define LOG_LEVEL LOG_DEBUG
#endif

/**
  Connect to a MQTT broker for remote logging.

  topic and clientID are kept, not copied: every later log line publishes to
  topic, and a reconnect uses clientID. Both must outlive the logger, so
  pass a literal or static storage, never a local buffer.

  Takes about LOG_LINE_MAX bytes of heap for a packet that holds a whole line,
  so every line up to LOG_LINE_MAX reaches the broker as it is printed.

  Blocks until it connects or has made max_retries + 1 attempts, 250 ms
  apart. An attempt on a host that does not answer waits out the TCP connect
  timeout, about 3 s, so 3 retries can hold a wake for about 13 s; a host that
  answers with no broker reply holds one attempt for 15 s.

  @param broker the hostname of the MQTT broker.
  @param port the port of the MQTT broker.
  @param topic the topic to publish logs to; see boardLogTopic().
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
  Keep the MQTT logging connection alive, and reconnect it once it drops.

  A board that stays awake calls it on every pass of its loop: the broker
  closes a connection that sends nothing for 1.5 keepalives, 22 s. A board
  that sleeps after each wake does not need it. A reconnect, tried at most
  every 30 s, can block for about 3 s when the broker's host does not answer.
*/
void keepMQTTConnected();

/**
  Drop every line above level from here on: LOG_ERROR keeps errors and worse,
  LOG_DEBUG keeps everything. A level above LOG_LEVEL is held at LOG_LEVEL,
  the most the build logs.

  @param level one of the LOG_* levels.
*/
void setLogLevel(uint16_t level);

/**
  Log a message. With its prefix, a line longer than LOG_LINE_MAX is cut, as
  logf() cuts it.

  Call log() and logf() from one task at a time, and never from an interrupt:
  the serial port, the MQTT client and the queue of unsent lines are shared,
  and nothing locks them.

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

#endif