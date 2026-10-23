// Update for the native_io tests: the image is kept in memory, and the test
// says whether begin() and end() succeed. end() does not check the MD5: a
// test reads md5 and written itself.
#ifndef EPD_FAKE_UPDATE_H
#define EPD_FAKE_UPDATE_H

#include <Arduino.h>

#include <string>

#define U_FLASH 0

class UpdateClass {
public:
    // What a test sets.
    bool beginOk = true;
    bool endOk = true;
    size_t writeLimit = (size_t)-1;  // a write past this many bytes falls short
    // What a test reads back.
    size_t size = 0;
    std::string written, md5;
    bool aborted = false, ended = false, rolledBack = false;

    bool begin(size_t len, int) {
        size = len;
        written.clear();
        md5.clear();
        aborted = ended = rolledBack = false;
        return beginOk;
    }
    size_t write(uint8_t* data, size_t len) {
        const size_t room = writeLimit > written.size() ? writeLimit - written.size() : 0;
        const size_t n = len < room ? len : room;
        written.append((const char*)data, n);
        return n;
    }
    bool setMD5(const char* hex) {
        md5 = hex;
        return true;
    }
    // Fails, as Update's does, on an image shorter than begin() was told.
    bool end() {
        ended = true;
        return endOk && written.size() == size;
    }
    void abort() { aborted = true; }
    bool rollBack() {
        rolledBack = true;
        return true;
    }
    const char* errorString() { return "fake update error"; }
};

extern UpdateClass Update;

#endif  // EPD_FAKE_UPDATE_H
