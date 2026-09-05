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
- :mod:`epd_server.mqtt`       subscribe to the client's remote log topic
- :mod:`epd_server.source`     DataSource protocol; Static / Composite helpers
- :mod:`epd_server.pipeline`   regenerate(): fetch what pages need, render, save
- :mod:`epd_server.app`        DisplayServer: routes, X-Next-* headers, regen loop
"""

from ._version import __version__  # noqa: E402

from .app import DisplayServer, align_process_timezone  # noqa: E402
from .config import (  # noqa: E402
    ConfigError,
    CoreConfig,
    FirmwareSettings,
    FirmwareSource,
    ImageSettings,
    MqttSettings,
    ServerSettings,
    load_core_config,
    load_yaml,
)
from .firmware import (  # noqa: E402
    ClientId,
    FirmwareImage,
    FirmwareStore,
    ReleaseWatcher,
    is_clean_tag,
    parse_user_agent,
    update_applies,
)
from .page import Page, SkipPage  # noqa: E402
from .pipeline import regenerate, select_pages  # noqa: E402
from .source import CompositeSource, DataSource, StaticSource  # noqa: E402
from .quantise import (  # noqa: E402
    GreyscaleQuantiser,
    IdentityQuantiser,
    PaletteQuantiser,
    Quantiser,
    grey_levels,
)
from .render import ChromiumRenderer, Renderer  # noqa: E402

__all__ = [
    "DisplayServer", "align_process_timezone",
    "ConfigError", "CoreConfig", "ServerSettings", "ImageSettings", "MqttSettings",
    "FirmwareSettings", "FirmwareSource", "load_core_config", "load_yaml",
    "ClientId", "FirmwareImage", "FirmwareStore", "ReleaseWatcher",
    "parse_user_agent", "is_clean_tag", "update_applies",
    "Page", "SkipPage",
    "DataSource", "StaticSource", "CompositeSource",
    "regenerate", "select_pages",
    "Renderer", "ChromiumRenderer",
    "Quantiser", "GreyscaleQuantiser", "PaletteQuantiser", "IdentityQuantiser",
    "grey_levels",
]
