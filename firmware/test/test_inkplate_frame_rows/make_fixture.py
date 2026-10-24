"""Write fixture.h: a crop of a page the server rendered, as an 8-bit grey PNG
whose rows cycle through all five PNG filters, and its pixels.

    python3 make_fixture.py <a page.png>

The pixels are stored two bits each: a page has only the greys 0, 85, 170
and 255.
"""
import struct
import sys
import zlib

from PIL import Image

GREYS = (0, 85, 170, 255)


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def filtered(rows):
    out, prev = bytearray(), bytes(len(rows[0]))
    for y, row in enumerate(rows):
        kind = y % 5
        out.append(kind)
        for x, v in enumerate(row):
            a = row[x - 1] if x else 0
            b, c = prev[x], prev[x - 1] if x else 0
            pred = (0, a, b, (a + b) // 2, paeth(a, b, c))[kind]
            out.append((v - pred) & 0xFF)
        prev = row
    return bytes(out)


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def main(page):
    im = Image.open(page).convert("L").crop((330, 560, 450, 640))
    w, h = im.size
    px = im.tobytes()
    assert set(px) <= set(GREYS), "a page has only four greys"
    rows = [px[y * w:(y + 1) * w] for y in range(h)]
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(filtered(rows), 9)) + chunk(b"IEND", b""))
    packed = bytearray((len(px) + 3) // 4)
    for i, v in enumerate(px):
        packed[i // 4] |= GREYS.index(v) << (2 * (i % 4))
    hexes = lambda b: ",".join(f"0x{x:02x}" for x in b)
    with open("fixture.h", "w") as f:
        f.write("// Made by make_fixture.py: a crop of a page the server rendered, as an\n"
                "// 8-bit grey PNG whose rows cycle through all five filters, and its\n"
                "// pixels, two bits each (0, 85, 170, 255).\n#pragma once\n#include <stdint.h>\n")
        f.write(f"static const int kFixtureWidth = {w};\nstatic const int kFixtureHeight = {h};\n")
        f.write(f"static const uint8_t kFixturePng[] = {{{hexes(png)}}};\n")
        f.write(f"static const uint8_t kFixturePixels[] = {{{hexes(packed)}}};\n")
    print(len(png), "bytes of PNG,", w, "x", h)


if __name__ == "__main__":
    main(sys.argv[1])
