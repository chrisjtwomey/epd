"""Regenerate pages from a data source.

This is the loop the server runs on a schedule. It is generic: it knows
nothing about weather, sensors or any particular page. Pages say what they
need via ``Page.requires``; the source says what it has via
``DataSource.datasets()``; this function joins the two.
"""
from __future__ import annotations

import logging
from typing import Iterable

from .page import Page, SkipPage
from .source import DataSource

log = logging.getLogger(__name__)


def select_pages(pages: Iterable[Page], only: str | Iterable[str] | None) -> list[Page]:
    """Pick the pages to regenerate.

    ``only`` may be ``None`` (all pages), one name, or several. A name
    matches either ``page.name`` or ``page.png_filename``, so both
    ``"today"`` and ``"today.png"`` work. Unknown names raise ``ValueError``
    rather than silently regenerating nothing.
    """
    pages = list(pages)
    if only is None:
        return pages
    wanted = {only} if isinstance(only, str) else set(only)
    selected = [p for p in pages if p.name in wanted or p.png_filename in wanted]
    matched = {p.name for p in selected} | {p.png_filename for p in selected}
    missing = wanted - matched
    if missing:
        known = ", ".join(p.png_filename for p in pages) or "(none)"
        raise ValueError(f"no page produces {sorted(missing)}; pages: {known}")
    return selected


def regenerate(
    pages: Iterable[Page],
    source: DataSource,
    only: str | Iterable[str] | None = None,
    force_refresh: bool = False,
) -> list[Page]:
    """Fetch what the selected pages need, render them, and save their PNGs.

    Each dataset is fetched **once** per call, however many pages need it.
    A page may raise :class:`~epd_server.page.SkipPage` from ``template()``
    to leave its existing PNG untouched; it is logged and left out of the
    returned list.

    Args:
        pages: every page the server knows about.
        source: where their content comes from.
        only: restrict to these page names / filenames (see :func:`select_pages`).
        force_refresh: call ``source.invalidate()`` first, so the fetches
            bypass any cache.

    Returns:
        The pages that were rendered and saved, in order.

    Raises:
        ValueError: ``only`` names a page that does not exist.
        KeyError: a page requires a dataset the source does not provide.
    """
    selected = select_pages(pages, only)
    if not selected:
        return []

    if force_refresh:
        source.invalidate()

    fetchers = source.datasets()
    needed: list[str] = []
    for page in selected:
        for name in page.requires:
            if name not in needed:
                needed.append(name)

    unknown = [n for n in needed if n not in fetchers]
    if unknown:
        available = ", ".join(sorted(fetchers)) or "(none)"
        raise KeyError(
            f"pages require dataset(s) {unknown} that the source does not provide; "
            f"available: {available}"
        )

    data = {name: fetchers[name]() for name in needed}

    rendered: list[Page] = []
    for page in selected:
        try:
            page.template(**{name: data[name] for name in page.requires})
        except SkipPage as why:
            page.log.warning("skipped %s: %s", page.png_filename, why)
            continue
        page.save()
        rendered.append(page)
    return rendered
