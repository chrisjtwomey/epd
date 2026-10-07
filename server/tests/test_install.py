"""The install page's helpers."""
from epd_server.install import install_page, server_name


def test_the_server_name_is_the_host_only_when_it_is_a_name():
    assert server_name("http://epd.local:8080") == "epd.local"
    assert server_name("http://192.168.1.2:8080") is None
    assert server_name("http://[fe80::1]:8080") is None
    assert server_name("") is None


def test_the_page_carries_its_config_as_json():
    page = install_page({"boards": [], "note": "a < b"})
    assert '{"boards": [], "note": "a \\u003c b"}' in page
