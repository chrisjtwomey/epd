// HTTPClient for the native_io tests: each request takes the next scripted
// answer, and is kept for the test to read.
#ifndef EPD_FAKE_HTTPCLIENT_H
#define EPD_FAKE_HTTPCLIENT_H

#include <Arduino.h>

#include <algorithm>
#include <deque>
#include <map>
#include <string>
#include <utility>
#include <vector>

#define HTTP_CODE_OK 200
#define HTTP_CODE_NOT_MODIFIED 304
#define HTTPC_ERROR_CONNECTION_REFUSED (-1)
#define HTTPC_ERROR_TOO_LESS_RAM (-8)
#define HTTPCLIENT_DEFAULT_TCP_TIMEOUT 5000

namespace fake {

// One answer. A body with no Content-Length is sent until it ends, as a
// chunked one is; stallAt stops the bytes there with the connection open.
struct HttpAnswer {
    int code = HTTP_CODE_OK;
    std::map<std::string, std::string> headers;
    std::string body;
    bool contentLength = true;
    size_t stallAt = std::string::npos;
};

struct HttpRequest {
    std::string method, url, userAgent, body;
    std::vector<std::pair<std::string, std::string>> headers;
    std::string header(const std::string& name) const {
        for (const auto& h : headers)
            if (String(h.first).equalsIgnoreCase(name)) return h.second;
        return "";
    }
};

struct Http {
    std::deque<HttpAnswer> answers;
    std::vector<HttpRequest> requests;
    void reset() {
        answers.clear();
        requests.clear();
    }
};

inline Http& http() {
    static Http h;
    return h;
}

}  // namespace fake

// The socket under an answer's body.
class WiFiClient {
public:
    void setNoDelay(bool) {}
    size_t available() const { return limit() - pos_; }
    int read(uint8_t* out, size_t len) {
        const size_t n = std::min(len, available());
        memcpy(out, body_.data() + pos_, n);
        pos_ += n;
        return (int)n;
    }
    // Open while bytes are owed, and for good once the answer stalls.
    bool open() const { return pos_ < body_.size(); }
    void load(const std::string& body, size_t stallAt) {
        body_ = body;
        stallAt_ = stallAt;
        pos_ = 0;
    }
    std::string rest() {
        std::string out = body_.substr(pos_, limit() - pos_);
        pos_ = limit();
        return out;
    }

private:
    size_t limit() const { return std::min(stallAt_, body_.size()); }
    std::string body_;
    size_t stallAt_ = std::string::npos;
    size_t pos_ = 0;
};

class HTTPClient {
public:
    void collectHeaders(const char* names[], size_t count) {
        collected_.assign(names, names + count);
    }
    void setUserAgent(const String& ua) { request_.userAgent = ua; }
    void setTimeout(uint32_t) {}
    bool begin(const String& url) {
        if (url.rfind("http://", 0) != 0 && url.rfind("https://", 0) != 0) return false;
        request_.url = url;
        return true;
    }
    // A second header of the same name replaces the first, as HTTPClient's does.
    void addHeader(const String& name, const String& value) {
        for (auto& h : request_.headers)
            if (String(h.first).equalsIgnoreCase(name)) {
                h.second = value;
                return;
            }
        request_.headers.emplace_back(name, value);
    }
    int GET() { return send("GET", ""); }
    int POST(uint8_t* body, size_t len) { return send("POST", std::string((const char*)body, len)); }
    // Only the headers named to collectHeaders(), matched without regard to
    // case, as HTTPClient's are.
    String header(const char* name) {
        bool collected = false;
        for (const auto& c : collected_) collected = collected || String(c).equalsIgnoreCase(name);
        if (!collected) return String();
        for (const auto& h : answer_.headers)
            if (String(h.first).equalsIgnoreCase(name)) return String(h.second);
        return String();
    }
    bool hasHeader(const char* name) { return !header(name).empty(); }
    int getSize() { return answer_.contentLength ? (int)answer_.body.size() : -1; }
    WiFiClient& getStream() { return stream_; }
    WiFiClient* getStreamPtr() { return &stream_; }
    bool connected() { return stream_.open(); }
    String getString() { return String(stream_.rest()); }
    void end() {}
    static String errorToString(int code) { return String("error ") + std::to_string(code); }

private:
    int send(const char* method, const std::string& body) {
        request_.method = method;
        request_.body = body;
        fake::http().requests.push_back(request_);
        if (fake::http().answers.empty()) {
            answer_ = fake::HttpAnswer();
            answer_.code = HTTPC_ERROR_CONNECTION_REFUSED;
            stream_.load("", std::string::npos);
            return answer_.code;
        }
        answer_ = fake::http().answers.front();
        fake::http().answers.pop_front();
        stream_.load(answer_.body, answer_.stallAt);
        return answer_.code;
    }

    std::vector<std::string> collected_;
    fake::HttpRequest request_;
    fake::HttpAnswer answer_;
    WiFiClient stream_;
};

#endif  // EPD_FAKE_HTTPCLIENT_H
