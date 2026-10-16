// Preferences.h stub for native host builds.
// One in-memory store for every namespace; a test empties it with clear().
#ifndef __STUB_PREFERENCES_H__
#define __STUB_PREFERENCES_H__

#include <map>
#include <string>

#include "Arduino.h"

class Preferences {
public:
    static std::map<std::string, std::string>& store() {
        static std::map<std::string, std::string> values;
        return values;
    }

    bool begin(const char*, bool) { return true; }
    void end() {}
    bool clear() { store().clear(); return true; }
    bool isKey(const char* key) { return store().count(key) > 0; }

    String getString(const char* key, const String& otherwise) {
        return isKey(key) ? String(store()[key]) : otherwise;
    }
    bool getBool(const char* key, bool otherwise) {
        return isKey(key) ? store()[key] == "1" : otherwise;
    }
    int getInt(const char* key, int otherwise) {
        return isKey(key) ? std::stoi(store()[key]) : otherwise;
    }

    size_t putString(const char* key, const std::string& value) {
        store()[key] = value;
        return value.size();
    }
    size_t putBool(const char* key, bool value) { return putString(key, value ? "1" : "0"); }
    size_t putInt(const char* key, int value) { return putString(key, std::to_string(value)); }
    size_t putBytes(const char* key, const void* value, size_t len) {
        return putString(key, std::string((const char*)value, len));
    }
    size_t getBytesLength(const char* key) { return isKey(key) ? store()[key].size() : 0; }
    size_t getBytes(const char* key, void* out, size_t len) {
        if (!isKey(key) || store()[key].size() > len) return 0;
        memcpy(out, store()[key].data(), store()[key].size());
        return store()[key].size();
    }
};

#endif // __STUB_PREFERENCES_H__
