"""Panel colour reduction in epd_server.quantise."""
import random

import pytest
from PIL import Image

from epd_server.quantise import (
    GreyscaleQuantiser,
    IdentityQuantiser,
    PaletteQuantiser,
    Quantiser,
    grey_levels,
)


def pixels(img):
    """Set of distinct pixel values without Image.getdata (deprecated in Pillow 14)."""
    raw = img.tobytes()
    n = len(img.getbands())
    if n == 1:
        return set(raw)
    return set(zip(*[raw[i::n] for i in range(n)]))


def _legacy_four_grey(img: Image.Image) -> Image.Image:
    """The algorithm Page.save() hardcoded before step 4, verbatim."""
    pal_img = Image.new("P", (1, 1))
    pal: list[int] = []
    for v in (0, 85, 170, 255):
        pal += [v, v, v]
    pal += [0] * (768 - len(pal))
    pal_img.putpalette(pal)
    return img.convert("RGB").quantize(
        colors=4, palette=pal_img, dither=Image.Dither.FLOYDSTEINBERG
    ).convert("L")


def _test_image(seed=0, size=(64, 48)) -> Image.Image:
    """Horizontal gradient with deterministic noise and a slight colour cast."""
    rnd = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        for x in range(w):
            base = int(255 * x / (w - 1)) + rnd.randint(-20, 20)
            v = max(0, min(255, base))
            g = max(0, min(255, v + rnd.randint(-10, 10)))
            px[x, y] = (v, g, v)
    return img


def _solid(value, size=(16, 16), mode="L") -> Image.Image:
    return Image.new(mode, size, value)


# ---------- the default must reproduce the old output exactly ----------

@pytest.mark.parametrize("seed", [0, 1, 7])
def test_default_greyscale_matches_legacy_algorithm_byte_for_byte(seed):
    img = _test_image(seed)
    new = GreyscaleQuantiser(levels=4).apply(img)
    old = _legacy_four_grey(img)
    assert new.mode == old.mode == "L"
    assert new.tobytes() == old.tobytes()


# ---------- grey_levels ----------

def test_grey_levels_are_evenly_spaced_and_hit_both_ends():
    assert grey_levels(2) == [0, 255]
    assert grey_levels(4) == [0, 85, 170, 255]
    assert grey_levels(8) == [0, 36, 73, 109, 146, 182, 219, 255]


def test_grey_levels_rejects_fewer_than_two():
    with pytest.raises(ValueError):
        grey_levels(1)


# ---------- GreyscaleQuantiser ----------

@pytest.mark.parametrize("levels", [2, 4, 8, 16])
def test_output_uses_only_the_allowed_levels(levels):
    out = GreyscaleQuantiser(levels).apply(_test_image())
    assert out.mode == "L"
    assert pixels(out) <= set(grey_levels(levels))


@pytest.mark.parametrize("value,expected", [(0, 0), (100, 85), (160, 170), (255, 255)])
def test_no_dither_maps_solid_patch_to_nearest_level(value, expected):
    out = GreyscaleQuantiser(4, dither=False).apply(_solid(value))
    assert pixels(out) == {expected}


def test_dither_spreads_a_midtone_across_levels():
    dithered = GreyscaleQuantiser(2, dither=True).apply(_solid(128))
    flat = GreyscaleQuantiser(2, dither=False).apply(_solid(128))
    assert pixels(dithered) == {0, 255}
    assert len(pixels(flat)) == 1


def test_accepts_non_rgb_input():
    out = GreyscaleQuantiser(4).apply(_solid((10, 200, 30, 255), mode="RGBA"))
    assert out.mode == "L"


# ---------- PaletteQuantiser ----------

def test_palette_output_uses_only_palette_colours():
    colors = [(0, 0, 0), (255, 255, 255), (255, 0, 0)]
    out = PaletteQuantiser(colors).apply(_test_image())
    assert out.mode == "RGB"
    assert pixels(out) <= set(colors)


def test_palette_maps_red_ish_to_red_without_dither():
    out = PaletteQuantiser([(0, 0, 0), (255, 255, 255), (255, 0, 0)], dither=False).apply(
        _solid((230, 20, 20), mode="RGB")
    )
    assert pixels(out) == {(255, 0, 0)}


@pytest.mark.parametrize("bad", [
    [],
    [(0, 0, 0)],
    [(0, 0, 0), (1, 2)],
    [(0, 0, 0), (0, 0, 300)],
    [(i, i, i) for i in range(257)],
])
def test_palette_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        PaletteQuantiser(bad)


# ---------- IdentityQuantiser / protocol ----------

def test_identity_returns_rgb_of_same_size():
    src = _solid(77, size=(9, 5))
    out = IdentityQuantiser().apply(src)
    assert out.mode == "RGB" and out.size == (9, 5)
    assert pixels(out) == {(77, 77, 77)}


def test_implementations_satisfy_the_protocol():
    assert isinstance(GreyscaleQuantiser(), Quantiser)
    assert isinstance(PaletteQuantiser([(0, 0, 0), (255, 255, 255)]), Quantiser)
    assert isinstance(IdentityQuantiser(), Quantiser)
    assert not isinstance(object(), Quantiser)
