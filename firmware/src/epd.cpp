#include "epd.h"

#include <stdlib.h>

#include "log_utils.h"

// The one board this program draws on. A pointer rather than a reference
// because it is not known until epdBegin(), and null until then is what lets
// a missing call be reported instead of guessed at.
static IBoard* theBoard = nullptr;

void epdBegin(IBoard& board) { theBoard = &board; }

IBoard& epdBoard() {
    if (theBoard == nullptr) {
        log(LOG_ERROR, "epdBegin() was never called: the library has no board");
        abort();
    }
    return *theBoard;
}
