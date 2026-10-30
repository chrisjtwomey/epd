"""The names a project may import: the package root, and the names
server/README.md's Modules table lists in each module. canary and
weather-cal import many of them from their modules, so a rename here
fails this test before it reaches either."""
import importlib

import epd_server

PUBLIC = {
    "epd_server.config": ["ConfigError", "CoreConfig", "FirmwareSettings", "MqttSettings",
                          "get_by_path", "get_prop", "get_prop_by_keys", "load_core_config",
                          "load_yaml"],
    "epd_server.registry": ["Registry"],
    "epd_server.cache": ["DEFAULT_TTL", "DiskCache"],
    "epd_server.page": ["Page", "SkipPage"],
    "epd_server.render": ["ChromiumRenderer", "Renderer"],
    "epd_server.quantise": ["GreyscaleQuantiser", "IdentityQuantiser", "PaletteQuantiser",
                            "Quantiser"],
    "epd_server.scheduling": ["Pools", "TimeRangesSchedule", "TimesSchedule", "WakeSchedule",
                              "next_regen", "next_wake", "seconds_until"],
    "epd_server.timeranges": ["DAYS", "MAX_RANGES", "TimeRanges", "Week", "check_interval",
                              "in_window", "parse_hhmm"],
    "epd_server.firmware": ["FirmwareStore", "ReleaseWatcher", "client_from_headers",
                            "is_clean_tag", "update_applies"],
    "epd_server.mqtt": ["client_log_subscriber"],
    "epd_server.certificate": ["certificate_names", "ensure_certificate"],
    "epd_server.board_keys": ["BoardKeys"],
    "epd_server.install": ["InstallBoard", "config_json"],
    "epd_server.network": ["network_settings_file"],
    "epd_server.source": ["CompositeSource", "DataSource", "Fetcher", "IngestSource",
                          "StaticSource"],
    "epd_server.store": ["ReadingsStore", "key"],
    "epd_server.pipeline": ["regenerate"],
    "epd_server.app": ["DisplayServer", "align_process_timezone"],
    "epd_server.headers": ["Wire"],
    "epd_server.logs": ["LEVELS", "LogStore", "LogsQuery", "MAX_LINES"],
    "epd_server.config_file": ["EDIT_ON_SERVER", "MISSING", "NOT_A_MAPPING", "NOT_YAML", "ON_SERVER", "Doc",
                               "FormError", "changed_paths", "flat", "lookup", "read", "reads_as",
                               "same", "twice"],
    "epd_server.settings_form": ["Edit", "Field", "FieldError", "Form", "Group", "Kind", "Pools", "Tab",
                                 "Writer", "as_input", "clock_time", "default_of", "host_zone", "initial",
                                 "input_text", "scaled", "words_of", "write_value"],
    "epd_server.login": ["Login", "SignInSite", "board_route", "guard", "sign_in_html"],
}


def test_every_public_name_is_in_its_module():
    missing = [f"{module}.{name}" for module, names in PUBLIC.items()
               for name in names if not hasattr(importlib.import_module(module), name)]
    assert missing == []


def test_every_name_the_root_lists_is_there():
    assert all(hasattr(epd_server, name) for name in epd_server.__all__)
    assert epd_server.__version__
