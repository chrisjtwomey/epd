#ifndef EPD_PROGRESS_BAR_H
#define EPD_PROGRESS_BAR_H

/**
  How a bar on the panel follows a firmware update's bytes, for the
  OtaProgress hook that takeOfferedUpdate() calls.

  The bar is drawn once with the whole panel, then gains a step with each
  partial update. There are ten steps: the Inkplate library makes every
  eleventh partial update a full one, which would flash the panel part way.
  Partial updates need the panel in black and white (IBoard::setBlackAndWhite).

  What the bar looks like, and what is drawn around it, is the project's.

      static ProgressBar bar;
      void onProgress(int done, int total) {
          switch (bar.update(done, total)) {
              case ProgressBar::FULL:    drawScreen(bar.filled); epdBoard().display(); break;
              case ProgressBar::PARTIAL: drawFill(bar.filled); epdBoard().partialDisplay(); break;
              case ProgressBar::NONE:    break;
          }
      }

  Pure: no hardware, no globals. Tested in test/test_progress_bar/.
*/
struct ProgressBar {
    static constexpr int kSteps = 10;

    enum Push { NONE, FULL, PARTIAL };

    // The steps on the panel; -1 until the bar is drawn.
    int filled = -1;

    // What to push for done of total bytes, with filled set to the steps to
    // draw: the whole panel at the first call, then a partial update each time
    // the bar gains a step. A total of 0 is not known yet.
    Push update(int done, int total) {
        const int step = total <= 0 || done <= 0 ? 0
                         : done >= total         ? kSteps
                                                 : (int)((long long)done * kSteps / total);
        if (filled < 0) {
            filled = step;
            return FULL;
        }
        if (step <= filled) return NONE;
        filled = step;
        return PARTIAL;
    }
};

#endif  // EPD_PROGRESS_BAR_H
