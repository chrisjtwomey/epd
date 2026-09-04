#ifndef __SETTINGS_H__
#define __SETTINGS_H__

/**
  The values a board cannot work without and a build server cannot know.

  An image built by CI carries placeholders for these, so the board keeps
  its own copy in non-volatile storage. A build flashed over USB with real
  values writes them there, and every image that arrives over the air reads
  them back. Everything else in defaults.h is code, and comes from the image.
*/
struct Settings {
    const char* serverURL;
    const char* wifiSSID;
    const char* wifiPass;
};

/** True for a value left as it came from defaults.example.cpp. */
bool isPlaceholder(const char* value);

/**
  Which of the two values to use: the image's when it is real, else the
  stored one, else the image's anyway so the failure names itself.
*/
const char* chooseSetting(const char* compiled, const char* stored);

/**
  Read the settings, storing any real value the running image carries.

  The returned pointers stay valid for the life of the program.
*/
Settings loadSettings();

#endif  // __SETTINGS_H__
