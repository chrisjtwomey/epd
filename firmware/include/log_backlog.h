#ifndef EPD_LOG_BACKLOG_H
#define EPD_LOG_BACKLOG_H

#include <stddef.h>

/**
  The log lines kept while the broker is unreachable, oldest first, in slots
  the caller owns: lineCount slots of lineBytes each. A full backlog drops
  its oldest line for the new one, and a line longer than a slot is cut.

  Pure: no hardware, no globals. Tested in test/test_log_backlog/.
*/
class LogBacklog {
public:
    LogBacklog(char* slots, size_t lineCount, size_t lineBytes)
        : slots_(slots), lines_(slots ? lineCount : 0), bytes_(lineBytes) {}

    void push(const char* line);

    /** Copy the oldest line into out, cut to fit, and drop it; false when empty. */
    bool pop(char* out, size_t outSize);

    size_t count() const { return count_; }

private:
    char* slots_;
    size_t lines_;
    size_t bytes_;
    size_t oldest_ = 0;
    size_t count_ = 0;
};

#endif
