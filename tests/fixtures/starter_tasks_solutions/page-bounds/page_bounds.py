"""Compute [start, end) slice indexes for a 1-based page of items."""

from __future__ import annotations


def page_bounds(total: int, page_size: int, page: int) -> tuple[int, int]:
    """Return the half-open ``(start, end)`` index range for ``page``.

    ``page`` is 1-based. A page beyond the last available page (or the
    trailing partial page) must clamp both bounds to ``total`` rather than
    returning indexes past the end of the collection.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if page < 1:
        raise ValueError("page must be >= 1")

    start = min((page - 1) * page_size, total)
    end = min(start + page_size, total)
    return (start, end)
