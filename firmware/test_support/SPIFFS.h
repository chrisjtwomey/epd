// SPIFFS.h stub for native host builds.
// image.cpp's page cache, on the host: every SPIFFS call fails, so the cache
// is always a miss, which is fine for the tests we care about (battery icon
// selection, sleep alarm arithmetic).
#ifndef __STUB_SPIFFS_H__
#define __STUB_SPIFFS_H__

#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

#define FILE_READ  "r"
#define FILE_WRITE "w"

// ps_malloc is PSRAM malloc on ESP32; map it to ordinary malloc on the host.
#define ps_malloc malloc

// Minimal File stub.  operator bool() always returns false so every
// SPIFFS.open() check falls through to the "no cache" path.
class File {
public:
    operator bool() const { return false; }
    size_t   size()                            { return 0; }
    size_t   read(uint8_t*, size_t)            { return 0; }
    size_t   write(const uint8_t*, size_t)     { return 0; }
    void     close()                           {}
};

class SPIFFSClass {
public:
    bool begin(bool = false) { return true; }
    File open(const char*, const char* = FILE_READ) { return File(); }
    bool remove(const char*) { return false; }
    bool rename(const char*, const char*) { return false; }
};

extern SPIFFSClass SPIFFS;

#endif // __STUB_SPIFFS_H__
