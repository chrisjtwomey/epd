// esp_ota_ops.h for the native_io tests: the running image's state, set by
// the test, and what the client asked of it.
#ifndef EPD_FAKE_ESP_OTA_OPS_H
#define EPD_FAKE_ESP_OTA_OPS_H

#include <esp_err.h>

typedef struct {
    int unused;
} esp_partition_t;

typedef enum {
    ESP_OTA_IMG_NEW = 0,
    ESP_OTA_IMG_PENDING_VERIFY = 1,
    ESP_OTA_IMG_VALID = 2,
    ESP_OTA_IMG_INVALID = 3,
    ESP_OTA_IMG_UNDEFINED = -1,
} esp_ota_img_states_t;

namespace fake {
struct Ota {
    esp_ota_img_states_t state = ESP_OTA_IMG_VALID;
    bool stateReadable = true;
    esp_err_t markValidResult = ESP_OK;
    int markedValid = 0, markedInvalid = 0;
};
inline Ota& ota() {
    static Ota o;
    return o;
}
}  // namespace fake

inline const esp_partition_t* esp_ota_get_running_partition() {
    static esp_partition_t running;
    return &running;
}
inline esp_err_t esp_ota_get_state_partition(const esp_partition_t*, esp_ota_img_states_t* out) {
    if (!fake::ota().stateReadable) return ESP_FAIL;
    *out = fake::ota().state;
    return ESP_OK;
}
inline esp_err_t esp_ota_mark_app_valid_cancel_rollback() {
    ++fake::ota().markedValid;
    return fake::ota().markValidResult;
}
inline esp_err_t esp_ota_mark_app_invalid_rollback_and_reboot() {
    ++fake::ota().markedInvalid;
    return ESP_FAIL;  // on a board this returns only when there is nothing to roll back to
}

#endif  // EPD_FAKE_ESP_OTA_OPS_H
