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

void FrameRows::writeGreyRows(int x, int y, const uint8_t* grey, int pitch, int rowCount,
                              int count) const {
    if (!(rotation & 1)) {
        for (int r = 0; r < rowCount; ++r) writeGreyRow(x, y + r, grey + r * pitch, count);
        return;
    }
    const int width = physicalHeight;    // as rotated
    const int height = physicalWidth;
    const int stride = physicalWidth / 2;
    const int first = y < 0 ? -y : 0;
    const int last = (y + rowCount > height ? height - y : rowCount) - 1;
    if (first > last) return;

    for (int i = 0; i < count; ++i) {
        const int xr = x + i;
        if (xr < 0 || xr >= width) continue;
        uint8_t* line = buffer + stride * ((rotation & 3) == 1 ? xr : width - 1 - xr);
        for (int r = first; r <= last; ++r) {
            const int yr = y + r;
            const int px = (rotation & 3) == 1 ? height - 1 - yr : yr;
            uint8_t* byte = line + (px >> 1);
            const uint8_t g = grey3(grey[r * pitch + i]);
            *byte = (px & 1) ? (uint8_t)((*byte & 0xF0) | g) : (uint8_t)((*byte & 0x0F) | (g << 4));
        }
    }
}
