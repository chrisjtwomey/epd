#ifndef EPD_CURRENT_BOARD_KEY_H
#define EPD_CURRENT_BOARD_KEY_H

#include "board_key.h"

/** The key this board signs with, read from the settings store the first time. */
const BoardKey& currentBoardKey();

#endif
