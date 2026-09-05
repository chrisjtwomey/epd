#ifndef __SETTINGS_H__
#define __SETTINGS_H__

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
    int wifiRetries;

    const char* ntpHost;
    const char* ntpTimezone;

    bool mqttEnabled;
    const char* mqttBroker;
    int mqttPort;
    const char* mqttClientID;
    const char* mqttTopic;
    int mqttRetries;
};

/** True for a value left as it came from defaults.example.cpp. */
bool isPlaceholder(const char* value);

/**
  Whether this image carries real MQTT settings, judged by the broker host.

  The block is resolved as a unit because its other fields cannot answer for
  themselves: false and "not set" are the same bool, and 1883 and localhost
  are plausible as both a real answer and a leftover default. The broker is
  the one field nobody leaves as a placeholder by accident.
*/
bool mqttSettingsAreSet(const char* broker);

/**
  Which of the two values to use: this build's when it is real, else the
  stored one, else this build's anyway so the failure names itself.
*/
const char* chooseSetting(const char* builtIn, const char* stored);

/**
  Resolve ``builtIn`` against the settings the board keeps for itself.

  Any real value the image carries is written to the store on the way past,
  so a build flashed over USB provisions the board for every image that
  arrives later; a placeholder is answered from the store instead. The
  returned pointers stay valid for the life of the program.

  ``builtIn`` is what this build carries. The library declares no settings
  symbols of its own, so what a project hard-codes, and where, is the
  project's business.
*/
ClientConfig loadConfig(const ClientConfig& builtIn);

#endif  // __SETTINGS_H__
