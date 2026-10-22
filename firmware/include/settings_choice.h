#ifndef EPD_SETTINGS_CHOICE_H
#define EPD_SETTINGS_CHOICE_H

/** True for a value left as it came from defaults.example.cpp. */
bool isPlaceholder(const char* value);

/**
  Which of the two values to use: this build's when it is real, else the
  stored one, else this build's anyway so the failure names itself.
*/
const char* chooseSetting(const char* builtIn, const char* stored);

#endif
