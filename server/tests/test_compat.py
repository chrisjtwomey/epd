"""Whether a board and a server can work together, judged by their versions."""
import pytest

from epd_server.compat import compatibility_key, compatible, version_order


@pytest.mark.parametrize("a, b, expected", [
    ("v0.2.2", "v0.2.2", True),
    ("v0.2.2", "v0.2.9", True),                     # a patch never breaks it
    ("v0.2.2", "v0.3.0", False),                    # before 1.0.0 a minor does
    ("v1.2.0", "v1.7.3", True),                     # after it only a major does
    ("v1.7.3", "v2.0.0", False),
    ("v0.9.0", "v1.0.0", False),
    ("v0.2.2-44-g2fe55a4-dirty", "v0.2.2", True),   # what git describe adds
    ("v0.2.2+build.7", "0.2.5", True),
    ("0.2.2", "V0.2.3", True),
])
def test_the_rule(a, b, expected):
    assert compatible(a, b) is expected
    assert compatible(b, a) is expected


@pytest.mark.parametrize("version", ["dev", "", None, "v0.2", "v0.2.2garbage", "2fe55a4"])
def test_what_is_not_a_version_cannot_be_judged(version):
    assert compatibility_key(version) is None
    assert compatible(version, "v0.2.2") is None


def test_builds_past_a_tag_sort_after_it_by_how_far_past():
    ordered = ["v0.3.1", "v0.3.1-1-g57fab37", "v0.3.1-4-gab12cd4", "v0.3.2"]
    assert sorted(reversed(ordered), key=version_order) == ordered
    assert version_order("v0.3.1-4-gab12cd4-dirty") == version_order("v0.3.1-4-gab12cd4")
    assert version_order("v0.3.1+build.7") == version_order("v0.3.1")
