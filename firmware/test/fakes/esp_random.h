// esp_random.h for the native_io tests: bytes a test can predict, which
// differ from one call to the next.
#ifndef EPD_FAKE_ESP_RANDOM_H
#define EPD_FAKE_ESP_RANDOM_H

#include <stddef.h>
#include <stdint.h>

inline void esp_fill_random(void* out, size_t len) {
    static uint8_t next = 1;
    for (size_t i = 0; i < len; ++i) ((uint8_t*)out)[i] = next += 7;
}

#endif  // EPD_FAKE_ESP_RANDOM_H
