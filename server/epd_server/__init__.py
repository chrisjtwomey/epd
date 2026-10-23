"""epd_server — scheduled HTML-to-PNG rendering for e-paper clients.

The pieces a project composes:

- :mod:`epd_server.config`     env-var-overridable lookups + typed core settings
- :mod:`epd_server.registry`   name -> class plugin registry
- :mod:`epd_server.cache`      JSON disk cache with per-key TTL
- :mod:`epd_server.page`       HTML page -> quantised PNG
- :mod:`epd_server.render`     Renderer protocol; ChromiumRenderer default
- :mod:`epd_server.quantise`   Quantiser protocol; greyscale / palette / identity
- :mod:`epd_server.scheduling` DST-correct next-wake / next-regen maths
- :mod:`epd_server.firmware`   which client an image is an update for; the image store
- :mod:`epd_server.mqtt`       subscribe to every board's remote log topic
- :mod:`epd_server.certificate` the self-signed certificate for the HTTPS port
- :mod:`epd_server.board_keys`  each board's key, paired over the air, and the signatures made with it
- :mod:`epd_server.network`    the network settings a USB flash writes to a board
- :mod:`epd_server.install`    the install page, and install-firmware.sh: firmware onto a board over USB
- :mod:`epd_server.logs`       LogStore: the boards' log lines, in SQLite, read back in order
- :mod:`epd_server.source`     DataSource protocol; Static / Composite / Ingest helpers
- :mod:`epd_server.store`      ReadingsStore: what a board posts, in SQLite, read back by time
- :mod:`epd_server.pipeline`   regenerate(): fetch what pages need, render, save
- :mod:`epd_server.app`        DisplayServer: routes, wire headers, regen loop; its parts
                               offers, install_routes, key_routes and responses are its own
- :mod:`epd_server.headers`    the header names, built from the product's prefix
"""

from ._version import __version__
from .app import DisplayServer, align_process_timezone
from .board_keys import BoardKeys
from .config import (
    ConfigError,
    CoreConfig,
    FirmwareSettings,
    FirmwareSource,
    ImageSettings,
    MqttSettings,
    NetworkSettings,
    ServerSettings,
    load_core_config,
    load_yaml,
)
from .firmware import (
    ClientId,
    FirmwareImage,
    FirmwareStore,
    ReleaseWatcher,
    is_clean_tag,
    update_applies,
)
from .install import InstallBoard
from .logs import LogStore
from .network import network_settings_file
from .page import Page, SkipPage
from .pipeline import regenerate, select_pages
from .quantise import (
    GreyscaleQuantiser,
    IdentityQuantiser,
    PaletteQuantiser,
    Quantiser,
    grey_levels,
)
from .render import ChromiumRenderer, Renderer
from .source import CompositeSource, DataSource, IngestSource, StaticSource
from .store import ReadingsStore

__all__ = [
    "__version__",
    "DisplayServer", "align_process_timezone",
    "BoardKeys",
    "ConfigError", "CoreConfig", "ServerSettings", "ImageSettings", "MqttSettings",
    "FirmwareSettings", "FirmwareSource", "NetworkSettings", "load_core_config", "load_yaml",
    "ClientId", "FirmwareImage", "FirmwareStore", "ReleaseWatcher",
    "is_clean_tag", "update_applies",
    "network_settings_file", "InstallBoard",
    "Page", "SkipPage",
    "DataSource", "StaticSource", "CompositeSource", "IngestSource", "ReadingsStore",
    "LogStore",
    "regenerate", "select_pages",
    "Renderer", "ChromiumRenderer",
    "Quantiser", "GreyscaleQuantiser", "PaletteQuantiser", "IdentityQuantiser",
    "grey_levels",
]
