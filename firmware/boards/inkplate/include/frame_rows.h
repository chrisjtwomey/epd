#ifndef EPD_FRAME_ROWS_H
#define EPD_FRAME_ROWS_H

#include <stdint.h>

/**
  A row of 8-bit grey pixels, written into an Inkplate's 3-bit frame buffer.

  The frame buffer holds two pixels a byte, the even column in the high
  nibble, at the panel's physical size. Each pixel lands where the library's
  drawPixel() puts it at that rotation, with the grey the library's PNG path
  gives it, RGB3BIT(v, v, v): so a page drawn a row at a time is the page the
  library draws a pixel at a time. Pixels off the panel are left out.

  Pure: no hardware, no globals. Tested in test/test_inkplate/.
*/
struct FrameRows {
    uint8_t* buffer;      // physicalWidth * physicalHeight / 2 bytes
    int16_t physicalWidth;
    int16_t physicalHeight;
    uint8_t rotation;     // 0-3, as Adafruit GFX counts them

    /** Write count greys at (x, y), (x + 1, y), ... in rotated coordinates. */
    void writeGreyRow(int x, int y, const uint8_t* grey, int count) const;

    /**
      Write rowCount rows of count greys, pitch bytes apart, from (x, y): the
      same pixels as writeGreyRow() for each row. On a panel turned sideways
      a row runs down a column of the frame buffer, so this writes a block of
      rows one panel row at a time, where a row at a time would touch a
      different panel row with every pixel.
    */
    void writeGreyRows(int x, int y, const uint8_t* grey, int pitch, int rowCount,
                       int count) const;
};

/** The 3-bit grey the library gives an 8-bit grey: RGB3BIT(v, v, v). */
uint8_t grey3(uint8_t v);

#endif  // EPD_FRAME_ROWS_H
