#ifndef EPD_BOARD_INKPLATE_H
#define EPD_BOARD_INKPLATE_H

/**
  The Inkplate IBoard, in one include.

      #include "EpdBoardInkplate.h"

  Which panel it drives is a build flag, not a different class: define
  ARDUINO_INKPLATE10, ARDUINO_INKPLATE6, ARDUINO_INKPLATE5V2 or another the
  Inkplate library supports, and InkplateBoard wraps whichever it compiles
  for.

  This is a library of its own so that a project on other hardware never
  pulls in the Inkplate driver. Write your own IBoard instead and depend on
  EpdClient alone; see docs/custom-board.md.
*/

#include "InkplateBoard.h"

#endif  // EPD_BOARD_INKPLATE_H
