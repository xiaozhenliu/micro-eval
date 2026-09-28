"""Check whether two half-open date ranges overlap."""

from __future__ import annotations

from datetime import date


def overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Return True if [a_start, a_end) intersects [b_start, b_end).

    Both ranges are half-open: the end date itself is not part of the
    range, so a range ending on 2026-01-05 and one starting on 2026-01-05
    are adjacent, not overlapping.
    """
    return a_start < b_end and b_start < a_end
