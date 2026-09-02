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
