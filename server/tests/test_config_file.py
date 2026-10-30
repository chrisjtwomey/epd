"""config.yaml as text: comments kept through an edit, and read as the server reads it."""
import pytest

from epd_server.config_file import (MISSING, Doc, FormError, changed_paths, lookup, read, reads_as,
                                    same, twice)

TEXT = """\
# The server's own settings.
server:
  port: 8080  # the panel fetches from here

# What shows.
display:
  pools:
    today: [today.png]  # the morning
    daily: [daily.png]
"""


def edited(text, path, value):
    doc = Doc(text)
    doc.set(path, value)
    return doc.text()


def test_an_untouched_file_comes_back_as_it_was():
    assert Doc(TEXT).text() == TEXT


def test_the_files_opening_marker_stays():
    assert Doc("---\n" + TEXT).text() == "---\n" + TEXT
    assert edited("---\na: 1\n", ("a",), 2) == "---\na: 2\n"


def test_a_new_value_changes_only_its_line():
    assert edited(TEXT, ("server", "port"), 9090) == TEXT.replace("port: 8080", "port: 9090")


def test_a_new_key_keeps_the_comments_and_the_blank_line():
    text = edited(TEXT, ("server", "timezone"), "Europe/Dublin")
    assert text == TEXT.replace("from here\n", "from here\n  timezone: Europe/Dublin\n")


def test_a_key_under_parents_that_do_not_exist_makes_them():
    assert read(edited("a: 1\n", ("b", "c", "d"), 2)) == {"a": 1, "b": {"c": {"d": 2}}}


def test_a_file_with_only_a_marker_and_comments_keeps_them():
    text = edited("---\n# Mine.\nserver:\n  port: 1\n", ("server", "port"), 2)
    assert "# Mine." in text and "port: 2" in text


def test_removing_the_last_key_removes_its_parent():
    doc = Doc("a:\n  b: 1\nc: 2\n")
    assert doc.remove(("a", "b")) and read(doc.text()) == {"c": 2}
    assert not doc.remove(("nothing", "here"))


@pytest.mark.parametrize("value", ["01:00", "12345678", "yes", "has # a: hash", "'quoted'", 'dou"ble"',
                                   "true", "1.5", "null", "~", " spaced "])
def test_a_string_reads_back_as_the_same_string(value):
    assert read(edited("a: 1\n", ("a",), value))["a"] == value


def test_setting_pools_keeps_their_comments_and_order():
    doc = Doc(TEXT)
    doc.set_pools({"daily": ["daily.png"], "today": ["today.png"], "new": ["a.png", "b.png"]})
    assert list(read(doc.text())["display"]["pools"]) == ["daily", "today", "new"]
    assert "# the morning" in doc.text()


def test_read_gives_what_the_server_reads():
    assert read("") == {}
    assert read("a: 1:00\n")["a"] == 60
    assert read("a: 01:00\n")["a"] == "01:00"


@pytest.mark.parametrize("text", ["a: [", "- a\n- b\n", "just text\n"])
def test_a_file_that_is_not_settings_is_refused(text):
    with pytest.raises(FormError):
        read(text)
    with pytest.raises(FormError):
        Doc(text)


def test_a_key_written_twice_names_both_lines():
    words = "a appears twice, on lines 1 and 2. Delete one: the server uses line 2."
    assert twice("a: 1\na: 2\n") == words
    assert twice("x:\n  a: 1\ny:\n  a: 2\n") is None
    with pytest.raises(FormError, match="on lines 1 and 2. Delete one in config.yaml on the server"):
        Doc("a: 1\na: 2\n")


def test_lookup_says_when_a_key_is_missing():
    assert lookup({"a": {"b": 1}}, ("a", "b")) == 1
    assert lookup({"a": 1}, ("a", "b")) is MISSING


def test_same_tells_a_number_from_its_digits_and_true_from_1():
    assert same(1, 1) and not same(1, "1") and not same(True, 1) and not same(MISSING, 1)


def test_changed_paths_names_only_what_changed():
    assert changed_paths({"a": {"b": 1, "c": 2}}, {"a": {"b": 1, "c": 3}, "d": 4}) == [("a", "c"), ("d",)]


def test_reads_as_checks_a_mapping_in_order():
    assert reads_as({"x": 1, "y": 2}, {"x": 1, "y": 2})
    assert not reads_as({"y": 2, "x": 1}, {"x": 1, "y": 2})
    assert reads_as(MISSING, MISSING) and not reads_as(1, MISSING)
