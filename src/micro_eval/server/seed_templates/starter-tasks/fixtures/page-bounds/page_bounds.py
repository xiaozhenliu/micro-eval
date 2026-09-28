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

    start = (page - 1) * page_size
    # BUG: neither bound is clamped to `total`, so the last (partial) page
    # and any page beyond the available range return an `end` (and
    # sometimes `start`) past the end of the collection instead of
    # collapsing to (total, total).
    end = start + page_size
    return (start, end)
