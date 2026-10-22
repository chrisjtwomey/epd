#ifndef EPD_SETTINGS_STORE_H
#define EPD_SETTINGS_STORE_H

#include <stdint.h>

#include "board_key.h"

/**
  The key this board shares with its server, from the settings store; not
  present before the board pairs. A USB install writes the store anew, and
  so leaves the board without a key until it pairs again.
*/
BoardKey loadBoardKey();

/** Keep ``key`` in the settings store, in place of any key before it. */
bool storeBoardKey(const uint8_t key[BOARD_KEY_LEN]);

#endif
