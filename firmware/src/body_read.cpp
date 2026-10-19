#include "body_read.h"

#include <stdint.h>

namespace {

// Longest line accepted around a chunk: a size, its extensions, a trailer.
const size_t kMaxLineBytes = 1024;

// The source, read with a stall limit counted from the last byte.
class Reader {
public:
    Reader(IBodySource& src, uint32_t stallMs)
        : src_(src), stallMs_(stallMs), lastByteMs_(src.nowMs()) {}

    // Waits until a byte is ready. False when the server closed (CutShort) or
    // stalled; failure() then says which.
    bool waitForBytes() {
        while (!src_.available()) {
            if (!src_.connected()) return fail(BodyRead::CutShort);
            if (src_.nowMs() - lastByteMs_ >= stallMs_) return fail(BodyRead::Stalled);
            src_.wait();
        }
        return true;
    }

    // Reads at least one byte, up to len, into out. A read that gives nothing
    // while bytes are ready counts towards the stall.
    bool readSome(uint8_t* out, size_t len, size_t* n) {
        for (;;) {
            if (!waitForBytes()) return false;
            const size_t ready = src_.available();
            *n = src_.read(out, ready < len ? ready : len);
            if (*n) {
                lastByteMs_ = src_.nowMs();
                return true;
            }
            if (src_.nowMs() - lastByteMs_ >= stallMs_) return fail(BodyRead::Stalled);
            src_.wait();
        }
    }

    // Reads exactly len bytes into out; *got counts them as they arrive.
    bool readExactly(uint8_t* out, size_t len, size_t* got) {
        size_t done = 0;
        while (done < len) {
            size_t n = 0;
            if (!readSome(out + done, len - done, &n)) return false;
            done += n;
            *got += n;
        }
        return true;
    }

    // Reads one line up to its '\n' and drops the '\r' before it. Keeps the
    // first outSize - 1 characters; a line past kMaxLineBytes is Malformed.
    bool readLine(char* out, size_t outSize) {
        size_t len = 0;
        for (size_t seen = 0;; ++seen) {
            if (seen == kMaxLineBytes) return fail(BodyRead::Malformed);
            uint8_t c = 0;
            size_t n = 0;
            if (!readSome(&c, 1, &n)) return false;
            if (c == '\n') break;
            if (len + 1 < outSize) out[len++] = (char)c;
        }
        if (len && out[len - 1] == '\r') --len;
        out[len] = '\0';
        return true;
    }

    bool fail(BodyRead why) {
        failure_ = why;
        return false;
    }

    BodyRead failure() const { return failure_; }

private:
    IBodySource& src_;
    const uint32_t stallMs_;
    uint32_t lastByteMs_;
    BodyRead failure_ = BodyRead::Malformed;
};

int hexValue(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

// The size at the start of a chunk's line: hex digits, then the end of the
// line or its extensions.
bool parseChunkSize(const char* line, size_t* size) {
    size_t value = 0;
    const char* at = line;
    for (int digit; (digit = hexValue(*at)) >= 0; ++at) {
        if (value > (SIZE_MAX >> 4)) return false;
        value = (value << 4) | (size_t)digit;
    }
    if (at == line) return false;
    if (*at != '\0' && *at != ';' && *at != ' ' && *at != '\t') return false;
    *size = value;
    return true;
}

}  // namespace

BodyRead readBody(IBodySource& src, int32_t expectedLen, uint8_t* buf, size_t capacity,
                  uint32_t stallMs, size_t* got) {
    *got = 0;
    Reader in(src, stallMs);
    if (expectedLen >= 0) {
        if ((size_t)expectedLen > capacity) return BodyRead::TooLong;
        return in.readExactly(buf, (size_t)expectedLen, got) ? BodyRead::Complete : in.failure();
    }
    while (in.waitForBytes()) {
        if (*got == capacity) return BodyRead::TooLong;
        size_t n = 0;
        if (!in.readSome(buf + *got, capacity - *got, &n)) break;
        *got += n;
    }
    return in.failure() == BodyRead::CutShort ? BodyRead::Complete : in.failure();
}

BodyRead readChunkedBody(IBodySource& src, uint8_t* buf, size_t capacity, uint32_t stallMs,
                         size_t* got) {
    *got = 0;
    Reader in(src, stallMs);
    char line[32];
    for (;;) {
        size_t size = 0;
        if (!in.readLine(line, sizeof(line))) return in.failure();
        if (!parseChunkSize(line, &size)) return BodyRead::Malformed;
        if (size == 0) break;
        if (size > capacity - *got) return BodyRead::TooLong;
        if (!in.readExactly(buf + *got, size, got)) return in.failure();
        if (!in.readLine(line, sizeof(line))) return in.failure();
        if (line[0]) return BodyRead::Malformed;
    }
    do {
        if (!in.readLine(line, sizeof(line))) return in.failure();
    } while (line[0]);
    return BodyRead::Complete;
}

const char* bodyReadName(BodyRead result) {
    switch (result) {
        case BodyRead::Complete: return "complete";
        case BodyRead::TooLong: return "longer than the buffer";
        case BodyRead::CutShort: return "connection closed early";
        case BodyRead::Stalled: return "server stopped sending";
        case BodyRead::Malformed: return "chunk sizes cannot be read";
    }
    return "unknown";
}
