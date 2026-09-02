#ifndef __MEM_UTILS_H__
#define __MEM_UTILS_H__

#include <stdlib.h>

#if defined(BOARD_HAS_PSRAM) && !defined(NATIVE)
#include <Arduino.h>
#endif

/**
  Allocate `size` bytes for a display or download buffer.

  Boards built with BOARD_HAS_PSRAM allocate from PSRAM first, because a
  full-panel PNG will not fit in the ordinary heap. The allocation falls back
  to the ordinary heap when PSRAM is absent or exhausted, so the firmware runs
  on boards that have no PSRAM at all.

  @param size the number of bytes to allocate.
  @returns a pointer to the allocation, or nullptr if it failed. The caller
  must check the result and free it with free().
*/
inline void* boardMalloc(size_t size) {
#if defined(BOARD_HAS_PSRAM) && !defined(NATIVE)
    void* psram = ps_malloc(size);
    if (psram) return psram;
#endif
    return malloc(size);
}

#endif  // __MEM_UTILS_H__
