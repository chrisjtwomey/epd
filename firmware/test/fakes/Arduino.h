// Arduino.h for the native_io tests: the public stub, plus a clock the test
// moves, FreeRTOS's tasks and semaphores, and ESP.restart().
#ifndef EPD_FAKE_ARDUINO_H
#define EPD_FAKE_ARDUINO_H

#include_next <Arduino.h>

#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>

// The clock: delay() moves it, so a wait that polls millis() ends at once.
namespace fake {
inline uint32_t& nowMs() {
    static uint32_t ms = 0;
    return ms;
}
}  // namespace fake

// The wall clock: 0, "not set", until setClock() sets it (see sys/time.h).
#include <time.h>
namespace fake {
inline time_t& clockSetTo() {
    static time_t t = 0;
    return t;
}
}  // namespace fake
inline time_t fake_time(time_t* out) {
    if (out) *out = fake::clockSetTo();
    return fake::clockSetTo();
}
#define time(out) fake_time(out)

inline uint32_t millis() { return fake::nowMs(); }
inline void delay(uint32_t ms) { fake::nowMs() += ms; }
inline void yield() {}

// FreeRTOS, as the sources use it. A task runs to its end inside
// xTaskCreate, so a task that waits on its caller cannot be modelled; a
// semaphore is a flag.
typedef uint32_t TickType_t;
typedef int BaseType_t;
typedef unsigned UBaseType_t;
typedef void (*TaskFunction_t)(void*);
typedef void* TaskHandle_t;
#define pdPASS 1
#define pdFAIL 0
#define pdTRUE 1
#define portMAX_DELAY 0xffffffffu
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))

struct FakeSemaphore {
    bool given = false;
};
typedef FakeSemaphore* SemaphoreHandle_t;

namespace fake {
// What the next xTaskCreate does: false refuses it, as with no memory.
inline bool& tasksCanStart() {
    static bool can = true;
    return can;
}
// Set by a semaphore wait, so a test can run what an event task would.
inline void (*&onSemaphoreWait())(TickType_t) {
    static void (*hook)(TickType_t) = nullptr;
    return hook;
}
}  // namespace fake

inline SemaphoreHandle_t xSemaphoreCreateBinary() { return new FakeSemaphore(); }
inline void vSemaphoreDelete(SemaphoreHandle_t s) { delete s; }
inline BaseType_t xSemaphoreGive(SemaphoreHandle_t s) {
    s->given = true;
    return pdTRUE;
}
inline BaseType_t xSemaphoreTake(SemaphoreHandle_t s, TickType_t ticks) {
    if (!s->given && ticks && fake::onSemaphoreWait()) fake::onSemaphoreWait()(ticks);
    if (!s->given) {
        if (ticks != portMAX_DELAY) delay(ticks);
        return pdFAIL;
    }
    s->given = false;
    return pdTRUE;
}
inline UBaseType_t uxTaskPriorityGet(TaskHandle_t) { return 1; }
inline BaseType_t xTaskCreate(TaskFunction_t fn, const char*, uint32_t, void* arg, UBaseType_t,
                              TaskHandle_t*) {
    if (!fake::tasksCanStart()) return pdFAIL;
    fn(arg);
    return pdPASS;
}
inline void vTaskDelete(TaskHandle_t) {}

// Arduino's byte streams, as far as YAMLDuino's declarations need them.
class Print {
public:
    virtual ~Print() {}
    virtual size_t write(uint8_t) = 0;
    virtual size_t write(const uint8_t* buf, size_t len) {
        size_t n = 0;
        while (n < len && write(buf[n])) ++n;
        return n;
    }
    int printf(const char* fmt, ...) {
        char line[256];
        va_list args;
        va_start(args, fmt);
        const int n = vsnprintf(line, sizeof(line), fmt, args);
        va_end(args);
        write((const uint8_t*)line, strlen(line));
        return n;
    }
};
class Stream : public Print {
public:
    virtual int available() = 0;
    virtual int read() = 0;
    virtual int peek() = 0;
    size_t readBytes(char* out, size_t len) {
        size_t n = 0;
        for (int c; n < len && (c = read()) >= 0;) out[n++] = (char)c;
        return n;
    }
    size_t readBytes(uint8_t* out, size_t len) { return readBytes((char*)out, len); }
};

// ESP.restart() returns here, and counts.
struct FakeEsp {
    int restarts = 0;
    void restart() { ++restarts; }
};
extern FakeEsp ESP;

#endif  // EPD_FAKE_ARDUINO_H
