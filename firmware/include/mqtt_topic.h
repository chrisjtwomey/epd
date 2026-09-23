#ifndef EPD_MQTT_TOPIC_H
#define EPD_MQTT_TOPIC_H

#include <stddef.h>

/**
  Write the topic a board publishes its log lines to: "<prefix>/<board>".

  One topic per board lets a server subscribe once, to "<prefix>/+", and
  still know which board sent each line, without parsing the line.

  Always null-terminates.

  @returns the length written, or 0 when it does not fit (out is then "").
*/
size_t boardLogTopic(const char* prefix, const char* board, char* out, size_t size);

#endif
