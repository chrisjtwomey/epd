"""epd_server — scheduled HTML-to-PNG rendering for e-paper clients.

The pieces a project composes:

- :mod:`epd_server.config`     resolve config values with env-var override
- :mod:`epd_server.registry`   name -> class plugin registry
- :mod:`epd_server.cache`      JSON disk cache with per-key TTL
- :mod:`epd_server.page`       HTML page -> quantised PNG
- :mod:`epd_server.render`     Renderer protocol; ChromiumRenderer default
- :mod:`epd_server.quantise`   Quantiser protocol; greyscale / palette / identity
- :mod:`epd_server.scheduling` DST-correct next-wake / next-regen maths
- :mod:`epd_server.mqtt`       subscribe to the client's remote log topic
"""

__version__ = "0.1.0"

from .page import Page  # noqa: E402
from .quantise import (  # noqa: E402
    GreyscaleQuantiser,
    IdentityQuantiser,
    PaletteQuantiser,
    Quantiser,
    grey_levels,
)
from .render import ChromiumRenderer, Renderer  # noqa: E402

__all__ = [
    "Page",
    "Renderer", "ChromiumRenderer",
    "Quantiser", "GreyscaleQuantiser", "PaletteQuantiser", "IdentityQuantiser",
    "grey_levels",
]
