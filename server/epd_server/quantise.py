"""Reduce a rendered image to the colours an e-paper panel can show.

:class:`Quantiser` is the protocol :class:`epd_server.page.Page` calls after
rendering. Pick the implementation for your panel:

- :class:`GreyscaleQuantiser` — ``levels`` evenly spaced greys. ``levels=4``
  is the default and matches 2-bit panels; ``levels=2`` is 1-bit mono;
  ``levels=8`` for 3-bit panels.
- :class:`PaletteQuantiser` — an explicit RGB palette, for 3-colour
  (black/white/red) or 7-colour ACeP panels.
- :class:`IdentityQuantiser` — no reduction; keep the RGB screenshot.

Dithering is Floyd–Steinberg by default. Turn it off with ``dither=False``
for flat, poster-like output.
"""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from PIL import Image

RGB = tuple[int, int, int]


@runtime_checkable
class Quantiser(Protocol):
    def apply(self, img: Image.Image) -> Image.Image:
        """Return a new image using only the panel's colours."""
        ...


def grey_levels(levels: int) -> list[int]:
    """``levels`` evenly spaced values from 0 to 255 inclusive."""
    if levels < 2:
        raise ValueError(f"levels must be >= 2 (got {levels})")
    return [round(i * 255 / (levels - 1)) for i in range(levels)]


class IdentityQuantiser:
    def apply(self, img: Image.Image) -> Image.Image:
        return img.convert("RGB")


class PaletteQuantiser:
    """Map every pixel to the nearest colour in ``colors`` (RGB triples)."""

    def __init__(self, colors: Sequence[RGB], dither: bool = True):
        colors = [tuple(int(c) for c in rgb) for rgb in colors]
        if not 2 <= len(colors) <= 256:
            raise ValueError(f"palette needs 2..256 colours (got {len(colors)})")
        for rgb in colors:
            if len(rgb) != 3 or not all(0 <= c <= 255 for c in rgb):
                raise ValueError(f"bad RGB triple {rgb!r}")
        self.colors: list[RGB] = colors  # type: ignore[assignment]
        self.dither = dither

        # PIL wants the palette as a 768-entry flat list on a "P" image.
        flat: list[int] = []
        for rgb in self.colors:
            flat.extend(rgb)
        flat += [0] * (768 - len(flat))
        self._palette_image = Image.new("P", (1, 1))
        self._palette_image.putpalette(flat)

    def _quantize(self, img: Image.Image) -> Image.Image:
        return img.convert("RGB").quantize(
            colors=len(self.colors),
            palette=self._palette_image,
            dither=Image.Dither.FLOYDSTEINBERG if self.dither else Image.Dither.NONE,
        )

    def apply(self, img: Image.Image) -> Image.Image:
        return self._quantize(img).convert("RGB")


class GreyscaleQuantiser(PaletteQuantiser):
    """``levels`` evenly spaced greys, returned as an 8-bit "L" image."""

    def __init__(self, levels: int = 4, dither: bool = True):
        self.levels = levels
        super().__init__([(v, v, v) for v in grey_levels(levels)], dither=dither)

    def apply(self, img: Image.Image) -> Image.Image:
        return self._quantize(img).convert("L")
