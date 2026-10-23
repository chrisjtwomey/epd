// What the native_io test suites share: reading the log, and scripting the
// server's answers.
#ifndef EPD_FAKE_IO_TEST_H
#define EPD_FAKE_IO_TEST_H

#include <HTTPClient.h>
#include <MqttLogger.h>

#include <string>

// Whether a line holding ``text`` was logged.
inline bool logged(const char* text) {
    for (const auto& line : fake::lines().serial)
        if (line.find(text) != std::string::npos) return true;
    return false;
}

// Queue the server's next answer.
inline fake::HttpAnswer& answer(int code, const std::string& body = "") {
    fake::HttpAnswer a;
    a.code = code;
    a.body = body;
    fake::http().answers.push_back(a);
    return fake::http().answers.back();
}

inline const fake::HttpRequest& lastRequest() { return fake::http().requests.back(); }

#endif  // EPD_FAKE_IO_TEST_H
