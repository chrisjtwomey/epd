"""The package version.

It sits in a module of its own because ``app`` needs it for the
``X-Server-Version`` header and ``__init__`` re-exports it, so it cannot
live in either without the two importing a circle.
"""

__version__ = "0.1.0"
