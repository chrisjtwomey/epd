// LittleFS for the native_io tests: files in memory, and the faults a test
// asks for: no mount, no file, a write that falls short, a failed rename.
#ifndef EPD_FAKE_LITTLEFS_H
#define EPD_FAKE_LITTLEFS_H

#include <Arduino.h>

#include <map>
#include <string>

#define FILE_READ "r"
#define FILE_WRITE "w"

class File {
public:
    File() = default;
    File(std::string* data, bool writing, size_t writeLimit)
        : data_(data), writing_(writing), writeLimit_(writeLimit) {
        if (writing_) data_->clear();
    }
    explicit operator bool() const { return data_ != nullptr; }
    size_t size() const { return data_ ? data_->size() : 0; }
    size_t write(const uint8_t* buf, size_t len) {
        if (!data_ || !writing_) return 0;
        const size_t room = writeLimit_ > data_->size() ? writeLimit_ - data_->size() : 0;
        const size_t n = len < room ? len : room;
        data_->append((const char*)buf, n);
        return n;
    }
    size_t read(uint8_t* buf, size_t len) {
        if (!data_ || writing_) return 0;
        const size_t n = len < data_->size() - pos_ ? len : data_->size() - pos_;
        memcpy(buf, data_->data() + pos_, n);
        pos_ += n;
        return n;
    }
    void close() { data_ = nullptr; }

private:
    std::string* data_ = nullptr;
    bool writing_ = false;
    size_t writeLimit_ = (size_t)-1;
    size_t pos_ = 0;
};

class LittleFSClass {
public:
    // What a test sets.
    bool mountOk = true;
    bool openOk = true;
    bool renameOk = true;
    size_t writeLimit = (size_t)-1;
    // The files, by path.
    std::map<std::string, std::string> files;

    bool begin(bool = false) { return mountOk; }
    File open(const char* path, const char* mode = FILE_READ) {
        if (!openOk) return File();
        const bool writing = std::string(mode) == FILE_WRITE;
        if (!writing && !files.count(path)) return File();
        return File(&files[path], writing, writeLimit);
    }
    bool exists(const char* path) { return files.count(path) > 0; }
    bool remove(const char* path) { return files.erase(path) > 0; }
    bool rename(const char* from, const char* to) {
        if (!renameOk || !files.count(from)) return false;
        files[to] = files[from];
        files.erase(from);
        return true;
    }
    void reset() {
        *this = LittleFSClass();
    }
};

extern LittleFSClass LittleFS;

#endif  // EPD_FAKE_LITTLEFS_H
