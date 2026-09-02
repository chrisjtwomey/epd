"""The generic regenerate() loop in epd_server.pipeline."""
import pytest

from epd_server.page import Page, SkipPage
from epd_server.pipeline import regenerate, select_pages
from epd_server.source import DataSource, StaticSource

from .test_source import Counting


class RecordingPage(Page):
    """A Page that records template kwargs and counts saves; never renders."""

    def __init__(self, name, requires=(), skip=False):
        super().__init__(name, 10, 10)
        self.requires = tuple(requires)
        self.skip = skip
        self.templated_with = None
        self.saves = 0

    def template(self, **kwargs):
        self.templated_with = kwargs
        if self.skip:
            raise SkipPage("nothing to show")

    def save(self):
        self.saves += 1


def pages():
    return [
        RecordingPage("today", ("map_url", "summary")),
        RecordingPage("hourly", ("map_url", "hours")),
        RecordingPage("daily", ("summary", "days")),
    ]


def source():
    return Counting(map_url="m", summary="s", hours="h", days="d")


# ---------- select_pages ----------

def test_select_none_means_all():
    ps = pages()
    assert select_pages(ps, None) == ps


@pytest.mark.parametrize("only", ["hourly", "hourly.png", ["hourly.png"], ("hourly", "daily.png")])
def test_select_by_name_or_filename(only):
    names = [p.name for p in select_pages(pages(), only)]
    expected = ["hourly"] if isinstance(only, str) or len(only) == 1 else ["hourly", "daily"]
    assert names == expected


def test_select_unknown_name_raises_with_known_list():
    with pytest.raises(ValueError, match=r"no page produces \['nope.png'\]; pages: today.png, hourly.png, daily.png"):
        select_pages(pages(), "nope.png")


# ---------- regenerate ----------

def test_regenerate_all_fetches_each_dataset_once_and_saves_every_page():
    ps, src = pages(), source()
    rendered = regenerate(ps, src)
    assert [p.name for p in rendered] == ["today", "hourly", "daily"]
    assert all(p.saves == 1 for p in ps)
    assert sorted(src.fetched) == ["days", "hours", "map_url", "summary"]  # once each
    assert ps[0].templated_with == {"map_url": "m", "summary": "s"}
    assert ps[2].templated_with == {"summary": "s", "days": "d"}


def test_regenerate_only_fetches_what_the_selected_page_needs():
    ps, src = pages(), source()
    rendered = regenerate(ps, src, only="daily.png")
    assert [p.name for p in rendered] == ["daily"]
    assert sorted(src.fetched) == ["days", "summary"]
    assert ps[0].saves == 0 and ps[1].saves == 0 and ps[2].saves == 1


def test_force_refresh_invalidates_before_fetching():
    src = source()
    regenerate(pages(), src, force_refresh=True)
    assert src.invalidated == 1
    src2 = source()
    regenerate(pages(), src2)
    assert src2.invalidated == 0


def test_skip_page_leaves_png_alone_and_is_not_returned():
    ps = [RecordingPage("a", ("summary",)), RecordingPage("b", ("summary",), skip=True)]
    rendered = regenerate(ps, StaticSource(summary="s"))
    assert [p.name for p in rendered] == ["a"]
    assert ps[1].templated_with == {"summary": "s"}   # template ran
    assert ps[1].saves == 0                           # save did not


def test_missing_dataset_is_a_clear_error_before_any_fetch():
    ps = [RecordingPage("a", ("summary", "pollen"))]
    src = source()
    with pytest.raises(KeyError, match=r"require dataset\(s\) \['pollen'\].*available: days, hours, map_url, summary"):
        regenerate(ps, src)
    assert src.fetched == []
    assert ps[0].saves == 0


def test_page_with_no_requires_still_renders():
    p = RecordingPage("static")
    assert regenerate([p], StaticSource()) == [p]
    assert p.templated_with == {} and p.saves == 1


def test_empty_page_list_is_a_noop():
    src = source()
    assert regenerate([], src) == []
    assert src.fetched == []
