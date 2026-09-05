#ifndef EPD_EPD_H
#define EPD_EPD_H

#include "IBoard.h"

/**
  Give the library the board it draws on. Call this before anything else.

  Until this runs the library has no board, and any call that needs one
  aborts rather than dereferencing nothing — that is a wiring mistake, and a
  panic with a backtrace says so more clearly than a crash later.

  The config is not passed here on purpose. A card, where there is one,
  overrides settings through applySdConfig(), and reading a card needs the
  board — so the config is not final until after this call. Holding a copy
  here would mean holding a stale one.
*/
void epdBegin(IBoard& board);

/** The board epdBegin() was given. Aborts if it was never called. */
IBoard& epdBoard();

#endif  // EPD_EPD_H
