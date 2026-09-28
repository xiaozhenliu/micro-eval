"""Parse a single CSV line, honoring double-quoted fields."""

from __future__ import annotations


def parse_csv_line(line: str) -> list[str]:
    """Split one CSV line into fields.

    A field wrapped in double quotes may contain commas and literal double
    quotes written as a doubled quote (``""``).
    """
    # BUG: naively splits on every comma, which breaks any quoted field
    # that itself contains a comma.
    return line.split(",")
