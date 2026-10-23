#ifndef EPD_SETTINGS_H
#define EPD_SETTINGS_H

#include <stdint.h>

/**
  Everything a wake needs that is not code: where the server is, how to reach
  the network, and where to send logs.

  Some of this an image built by a release pipeline cannot carry — the server
  URL, the network name and its password, and where to send logs — so the
  board keeps its own copy. The rest comes from the image. A card, where
  there is one, overrides any of it.
*/
struct ClientConfig {
    const char* serverURL;
    int serverRetries;
    uint32_t defaultRefreshSeconds;

    const char* wifiSSID;
    const char* wifiPass;
    int wifiConnectTimeoutSeconds;

    bool mqttEnabled;
    const char* mqttBroker;
    int mqttPort;
    const char* mqttClientID;
    // Each board logs to <mqttPrefix>/<CLIENT_NAME>: see boardLogTopic().
    const char* mqttPrefix;
    int mqttRetries;
};

/**
  Whether this image carries real MQTT settings, judged by the broker host.

  The block is resolved as a unit because its other fields cannot answer for
  themselves: false and "not set" are the same bool, and 1883 and localhost
  are plausible as both a real answer and a leftover default. The broker is
  the one field nobody leaves as a placeholder by accident.
*/
bool mqttSettingsAreSet(const char* broker);

/**
  Resolve ``builtIn`` against the settings the board keeps for itself.

  Any real value the image carries is written to the store on the way past,
  so a build flashed over USB provisions the board for every image that
  arrives later; a placeholder is answered from the store instead.

  Call it once. The returned strings stay valid until the next call, which
  replaces them, and configureWiFi() keeps the SSID and password it is given.

  ``builtIn`` is what this build carries. The library declares no settings
  symbols of its own, so what a project hard-codes, and where, is the
  project's business.
*/
ClientConfig loadConfig(const ClientConfig& builtIn);

#endif  // EPD_SETTINGS_H