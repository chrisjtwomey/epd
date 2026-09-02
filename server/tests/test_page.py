"""Layout geometry and output paths in epd_server.page."""
import pytest

from epd_server.page import Page


def test_layout_css_variables_reflect_left_bottom_alignment():
    page = Page("dummy", 825, 1200, inner_width=650, inner_height=900,
                inner_align_x="left", inner_align_y="bottom")
    style = page.layout_css_variables()
    assert "--inner-pad-left:0px;" in style
    assert "--inner-pad-right:175px;" in style
    assert "--inner-pad-top:300px;" in style
    assert "--inner-pad-bottom:0px;" in style


def test_layout_css_variables_center_splits_slack_evenly():
    page = Page("dummy", 800, 600, inner_width=600, inner_height=400)
    style = page.layout_css_variables()
    assert "--inner-pad-left:100.0px;" in style
    assert "--inner-pad-right:100.0px;" in style
    assert "--inner-pad-top:100.0px;" in style
    assert "--inner-pad-bottom:100.0px;" in style


def test_inner_defaults_to_outer():
    page = Page("dummy", 825, 1200)
    assert page.image_inner_width == 825
    assert page.image_inner_height == 1200
    assert "--inner-pad-left:0" in page.layout_css_variables()


def test_paths_come_from_configured_dirs(tmp_path):
    page = Page("today", 10, 10, html_dir=tmp_path / "html", png_dir=tmp_path)
    assert page.html_path == str(tmp_path / "html" / "today.html")
    assert page.png_path == str(tmp_path / "today.png")


def test_save_without_dirs_is_a_clear_error():
    page = Page("today", 10, 10)
    with pytest.raises(ValueError, match="html_dir"):
        page.html_path
    with pytest.raises(ValueError, match="png_dir"):
        page.png_path


def test_template_is_abstract():
    with pytest.raises(NotImplementedError):
        Page("dummy", 10, 10).template()


# ---------- save(): the render -> quantise -> write pipeline ----------

from airium import Airium
from PIL import Image


def pixels(img):
    """Set of distinct pixel values without Image.getdata (deprecated in Pillow 14)."""
    raw = img.tobytes()
    n = len(img.getbands())
    if n == 1:
        return set(raw)
    return set(zip(*[raw[i::n] for i in range(n)]))


class FakeRenderer:
    """Returns a fixed image and records what it was asked to render."""

    def __init__(self, img):
        self.img = img
        self.calls = []

    def render(self, html_path, width, height):
        self.calls.append((html_path, width, height))
        return self.img.copy()


class HelloPage(Page):
    def template(self, **kwargs):
        self.airium = Airium()
        a = self.airium
        a("<!DOCTYPE html>")
        with a.html():
            a.p(_t="hello")


def test_save_writes_html_then_a_default_four_grey_png(tmp_path):
    grey = Image.new("RGB", (40, 30), (120, 120, 120))
    renderer = FakeRenderer(grey)
    page = HelloPage("today", 40, 30, html_dir=tmp_path / "html", png_dir=tmp_path,
                     renderer=renderer)
    page.template()
    page.save()

    html = (tmp_path / "html" / "today.html").read_text()
    assert html.startswith("<!DOCTYPE html>") and "hello" in html
    assert renderer.calls == [(str(tmp_path / "html" / "today.html"), 40, 30)]

    out = Image.open(tmp_path / "today.png")
    assert out.mode == "L" and out.size == (40, 30)
    assert pixels(out) <= {0, 85, 170, 255}


def test_save_uses_the_supplied_quantiser(tmp_path):
    class AllRed:
        def apply(self, img):
            return Image.new("RGB", img.size, (255, 0, 0))

    page = HelloPage("x", 8, 8, html_dir=tmp_path, png_dir=tmp_path,
                     renderer=FakeRenderer(Image.new("RGB", (8, 8))), quantiser=AllRed())
    page.template()
    page.save()
    out = Image.open(tmp_path / "x.png")
    assert out.mode == "RGB" and pixels(out) == {(255, 0, 0)}


def test_save_creates_missing_output_dirs(tmp_path):
    page = HelloPage("x", 4, 4, html_dir=tmp_path / "a" / "b", png_dir=tmp_path / "c",
                     renderer=FakeRenderer(Image.new("RGB", (4, 4))))
    page.template()
    page.save()
    assert (tmp_path / "a" / "b" / "x.html").exists()
    assert (tmp_path / "c" / "x.png").exists()
