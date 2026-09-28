"""Parse a single CSV line, honoring double-quoted fields."""

from __future__ import annotations


def parse_csv_line(line: str) -> list[str]:
    """Split one CSV line into fields.

    A field wrapped in double quotes may contain commas and literal double
    quotes written as a doubled quote (``""``).
    """
    fields: list[str] = []
    current: list[str] = []
    in_quotes = False
    i = 0
    length = len(line)
    while i < length:
        char = line[i]
        if in_quotes:
            if char == '"':
                if i + 1 < length and line[i + 1] == '"':
                    current.append('"')
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            current.append(char)
            i += 1
            continue
        if char == '"':
            in_quotes = True
            i += 1
            continue
        if char == ",":
            fields.append("".join(current))
            current = []
            i += 1
            continue
        current.append(char)
        i += 1
    fields.append("".join(current))
    return fields
