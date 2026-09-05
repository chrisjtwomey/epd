// WiFi.h stub for native host builds.
// app.cpp turns the radio off before it sleeps. The counter records when,
// so a test can prove the update step still had a network.
#ifndef __STUB_WIFI_H__
#define __STUB_WIFI_H__

#define WIFI_OFF 0

class WiFiClass {
public:
    int disconnectCount = 0;
    void disconnect() { ++disconnectCount; }
    void mode(int)    {}
};

extern WiFiClass WiFi;

#endif // __STUB_WIFI_H__
