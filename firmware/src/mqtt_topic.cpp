#include "mqtt_topic.h"

#include <stdio.h>

size_t boardLogTopic(const char* prefix, const char* board, char* out, size_t size) {
    if (size == 0) return 0;
    const int n = snprintf(out, size, "%s/%s", prefix, board);
    if (n < 0 || (size_t)n >= size) {
        out[0] = '\0';
        return 0;
    }
    return (size_t)n;
}
