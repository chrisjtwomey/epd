"""Render an HTML page to a quantised PNG sized for an e-paper panel.

Subclass :class:`Page`, build the document into ``self.airium`` in
:meth:`Page.template`, then call :meth:`Page.save` to write the HTML,
screenshot it, and reduce it to the panel's colours.

Two collaborators are pluggable, both with sensible defaults:

- ``renderer`` — a :class:`~epd_server.render.Renderer`; default
  :class:`~epd_server.render.ChromiumRenderer`.
- ``quantiser`` — a :class:`~epd_server.quantise.Quantiser`; default
  :class:`~epd_server.quantise.GreyscaleQuantiser` with four levels.

Two directories are involved, and they are usually different:

- ``html_dir`` — where the ``.html`` lands. Put it beside the page's CSS,
  icons and fonts so relative ``href``/``src`` links resolve when Chromium
  loads it from ``file://``.
- ``png_dir`` — where the finished ``.png`` lands, for the HTTP server to
  serve.

Layout is expressed as an *outer* canvas (the PNG size) and an *inner* box
the content is constrained to, aligned within the outer canvas. Pages read
the result as CSS custom properties from :meth:`Page.layout_css_variables`.

A page declares the datasets its :meth:`Page.template` needs in
:attr:`Page.requires`; :func:`epd_server.pipeline.regenerate` fetches them
from a :class:`~epd_server.source.DataSource` and passes them as keyword
arguments. ``template()`` may raise :class:`SkipPage` to leave the existing
PNG untouched — for example when the data for that page is not available.
"""
from __future__ import annotations

import logging
import os

from airium import Airium

from .quantise import GreyscaleQuantiser, Quantiser
from .render import ChromiumRenderer, Renderer


class SkipPage(Exception):
    """Raise from ``Page.template()`` to skip rendering this page this time."""


class Page:
    #: Dataset names this page's template() needs, in the order it wants them.
    #: The pipeline passes each one as a keyword argument of the same name.
    requires: tuple[str, ...] = ()

    def __init__(
        self,
        name: str,
        width: int,
        height: int,
        inner_width: int | None = None,
        inner_height: int | None = None,
        inner_align_x: str = "center",
        inner_align_y: str = "center",
        html_dir: str | os.PathLike | None = None,
        png_dir: str | os.PathLike | None = None,
        renderer: Renderer | None = None,
        quantiser: Quantiser | None = None,
    ):
        self.name = name
        self.image_width = width
        self.image_height = height
        self.image_inner_width = inner_width if inner_width is not None else width
        self.image_inner_height = inner_height if inner_height is not None else height
        self.image_inner_align_x = inner_align_x
        self.image_inner_align_y = inner_align_y
        self.html_dir = os.fspath(html_dir) if html_dir is not None else None
        self.png_dir = os.fspath(png_dir) if png_dir is not None else None
        # Defaults are created lazily in save(), so constructing a Page stays
        # cheap and side-effect free.
        self.renderer = renderer
        self.quantiser = quantiser

        self.airium = Airium()

    @property
    def log(self):
        return logging.getLogger(self.name)

    # ── Paths ────────────────────────────────────────────────────────────

    @property
    def png_filename(self) -> str:
        """The file the server serves for this page, e.g. ``"today.png"``."""
        return self.name + ".png"

    @property
    def html_path(self) -> str:
        if self.html_dir is None:
            raise ValueError(f"Page {self.name!r} has no html_dir; cannot save")
        return os.path.join(self.html_dir, self.name + ".html")

    @property
    def png_path(self) -> str:
        if self.png_dir is None:
            raise ValueError(f"Page {self.name!r} has no png_dir; cannot save")
        return os.path.join(self.png_dir, self.name + ".png")

    # ── Rendering ────────────────────────────────────────────────────────

    def template(self, **kwargs):
        raise NotImplementedError(
            "Page {} should implement function {}".format(
                self.__class__.__name__, self.template.__name__
            )
        )

    def save(self):
        """Write the HTML, render it, quantise it, and write the PNG."""
        html_fp = self.html_path
        png_fp = self.png_path

        os.makedirs(os.path.dirname(html_fp), exist_ok=True)
        os.makedirs(os.path.dirname(png_fp), exist_ok=True)
        with open(html_fp, "wb") as f:
            f.write(bytes(self.airium))

        renderer = self.renderer if self.renderer is not None else ChromiumRenderer()
        quantiser = self.quantiser if self.quantiser is not None else GreyscaleQuantiser(levels=4)

        img = renderer.render(html_fp, self.image_width, self.image_height)
        img = quantiser.apply(img)
        img.save(png_fp, format="png", optimize=True)

        self.log.info("Rendered %s -> %s", os.path.basename(html_fp), os.path.basename(png_fp))

    # ── Layout ───────────────────────────────────────────────────────────

    def layout_css_variables(self) -> str:
        """CSS custom properties describing the outer/inner canvas geometry."""
        slack_x = max(self.image_width - self.image_inner_width, 0)
        slack_y = max(self.image_height - self.image_inner_height, 0)
        inner_vw = self.image_inner_width / 100.0
        inner_vh = self.image_inner_height / 100.0

        if self.image_inner_align_x == "left":
            pad_left, pad_right = 0, slack_x
        elif self.image_inner_align_x == "right":
            pad_left, pad_right = slack_x, 0
        else:
            pad_left = slack_x / 2
            pad_right = slack_x - pad_left

        if self.image_inner_align_y == "top":
            pad_top, pad_bottom = 0, slack_y
        elif self.image_inner_align_y == "bottom":
            pad_top, pad_bottom = slack_y, 0
        else:
            pad_top = slack_y / 2
            pad_bottom = slack_y - pad_top

        return (
            f"--outer-width:{self.image_width}px;"
            f"--outer-height:{self.image_height}px;"
            f"--inner-width:{self.image_inner_width}px;"
            f"--inner-height:{self.image_inner_height}px;"
            f"--inner-vw:{inner_vw}px;"
            f"--inner-vh:{inner_vh}px;"
            f"--inner-pad-left:{pad_left}px;"
            f"--inner-pad-right:{pad_right}px;"
            f"--inner-pad-top:{pad_top}px;"
            f"--inner-pad-bottom:{pad_bottom}px;"
        )
