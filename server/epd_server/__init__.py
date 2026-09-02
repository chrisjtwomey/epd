"""epd_server — scheduled HTML-to-PNG rendering for e-paper clients.

The pieces a project composes:

- :mod:`epd_server.config`     resolve config values with env-var override
- :mod:`epd_server.registry`   name -> class plugin registry
- :mod:`epd_server.cache`      JSON disk cache with per-key TTL
- :mod:`epd_server.page`       HTML page -> quantised PNG via headless Chromium
- :mod:`epd_server.scheduling` DST-correct next-wake / next-regen maths
- :mod:`epd_server.mqtt`       subscribe to the client's remote log topic
"""

__version__ = "0.1.0"
