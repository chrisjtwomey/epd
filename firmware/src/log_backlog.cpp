#include "log_backlog.h"

#include <string.h>

namespace {

// Copy text into out, cut to fit, always terminated.
void copyCut(char* out, size_t size, const char* text) {
    if (!size) return;
    size_t n = strlen(text);
    if (n > size - 1) n = size - 1;
    memcpy(out, text, n);
    out[n] = '\0';
}

}  // namespace

void LogBacklog::push(const char* line) {
    if (!lines_ || bytes_ == 0) return;
    size_t slot;
    if (count_ == lines_) {
        slot = oldest_;
        oldest_ = (oldest_ + 1) % lines_;
    } else {
        slot = (oldest_ + count_) % lines_;
        ++count_;
    }
    copyCut(slots_ + slot * bytes_, bytes_, line);
}

bool LogBacklog::pop(char* out, size_t outSize) {
    if (!count_) return false;
    copyCut(out, outSize, slots_ + oldest_ * bytes_);
    oldest_ = (oldest_ + 1) % lines_;
    --count_;
    return true;
}
