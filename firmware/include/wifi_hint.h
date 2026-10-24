#ifndef EPD_WIFI_HINT_H
#define EPD_WIFI_HINT_H

#include <stdint.h>
#include <string.h>

/**
  The access point a board last joined, kept through deep sleep so that the
  next wake joins it on its channel, without first scanning every channel.

  It is kept for one network: a hint for another SSID is not used.

  Pure: no hardware, no globals. Tested in test/test_wifi_hint/.
*/
struct WifiHint {
    uint32_t ssidHash;
    uint8_t channel;  // 0 when none is kept
    uint8_t bssid[6];

    bool usableFor(const char* ssid) const { return channel != 0 && ssidHash == hash(ssid); }

    void keep(const char* ssid, uint8_t joinedChannel, const uint8_t* joinedBssid) {
        if (!joinedChannel || !joinedBssid) {
            forget();
            return;
        }
        ssidHash = hash(ssid);
        channel = joinedChannel;
        memcpy(bssid, joinedBssid, sizeof(bssid));
    }

    void forget() { channel = 0; }

    // FNV-1a: an SSID is up to 32 bytes, and the hint needs only to tell one
    // network from another.
    static uint32_t hash(const char* s) {
        uint32_t h = 2166136261u;
        for (; s && *s; ++s) h = (h ^ (uint8_t)*s) * 16777619u;
        return h;
    }
};

#endif  // EPD_WIFI_HINT_H
