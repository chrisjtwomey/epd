// The objects the fakes declare. Each native_io test suite includes this in
// its one test file.
#ifndef EPD_FAKE_GLOBALS_H
#define EPD_FAKE_GLOBALS_H

#include <Arduino.h>
#include <LittleFS.h>
#include <Update.h>
#include <WiFi.h>
#include <driver/rtc_io.h>

WiFiClass WiFi;
LittleFSClass LittleFS;
UpdateClass Update;
FakeEsp ESP;
HardwareSerial Serial;
esp_sleep_wakeup_cause_t g_wakeup_cause = ESP_SLEEP_WAKEUP_UNDEFINED;
uint64_t g_timerWakeupUs = 0;

#endif  // EPD_FAKE_GLOBALS_H
