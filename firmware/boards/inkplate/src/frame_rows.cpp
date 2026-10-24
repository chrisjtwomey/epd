#include "frame_rows.h"

uint8_t grey3(uint8_t v) {
    // RGB8BIT(v, v, v) is (256 * v) >> 8, which is v.
    return (uint8_t)((v * 7UL + 127UL) / 255UL);
}

void FrameRows::writeGreyRow(int x, int y, const uint8_t* grey, int count) const {
    const bool sideways = rotation & 1;
    const int width = sideways ? physicalHeight : physicalWidth;    // as rotated
    const int height = sideways ? physicalWidth : physicalHeight;
    if (y < 0 || y >= height) return;
    const int stride = physicalWidth / 2;

    for (int i = 0; i < count; ++i) {
        const int xr = x + i;
        if (xr < 0 || xr >= width) continue;
        int px, py;  // on the panel
        switch (rotation & 3) {
            case 1: px = height - 1 - y; py = xr; break;
            case 2: px = width - 1 - xr; py = height - 1 - y; break;
            case 3: px = y; py = width - 1 - xr; break;
            default: px = xr; py = y; break;
        }
        uint8_t* byte = buffer + stride * py + (px >> 1);
        const uint8_t g = grey3(grey[i]);
        *byte = (px & 1) ? (uint8_t)((*byte & 0xF0) | g) : (uint8_t)((*byte & 0x0F) | (g << 4));
    }
}
