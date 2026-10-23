// sys/time.h for the native_io tests: setting the clock moves the test's
// clock (see Arduino.h), and leaves the computer's clock alone.
#ifndef EPD_FAKE_SYS_TIME_H
#define EPD_FAKE_SYS_TIME_H

#include_next <sys/time.h>

#include <Arduino.h>

static inline int fake_settimeofday(const struct timeval* tv, const void*) {
    fake::clockSetTo() = tv->tv_sec;
    return 0;
}
#define settimeofday fake_settimeofday

#endif  // EPD_FAKE_SYS_TIME_H
