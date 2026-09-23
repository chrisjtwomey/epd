#ifndef EPD_WIFI_RETRY_H
#define EPD_WIFI_RETRY_H

#include <stdint.h>

/**
  When a board that stays awake starts a new Wi-Fi connection attempt.

  While the link is down, an attempt is due every interval, counted from when
  the link was first seen down. The first interval is left to the framework's
  own reconnect.

  Pure: no hardware, no globals. Tested in test/test_wifi_retry/.
*/
class WifiRetry {
public:
    explicit WifiRetry(uint32_t intervalMs) : interval_(intervalMs) {}

    /** True when an attempt is due now. */
    bool due(uint32_t nowMs, bool connected) {
        if (connected) {
            down_ = false;
            return false;
        }
        if (!down_) {
            down_ = true;
            downSinceMs_ = lastTryMs_ = nowMs;
            return false;
        }
        if (nowMs - lastTryMs_ < interval_) return false;
        lastTryMs_ = nowMs;
        return true;
    }

    bool down() const { return down_; }
    uint32_t downForMs(uint32_t nowMs) const { return down_ ? nowMs - downSinceMs_ : 0; }

private:
    uint32_t interval_;
    bool down_ = false;
    uint32_t downSinceMs_ = 0;
    uint32_t lastTryMs_ = 0;
};

#endif
