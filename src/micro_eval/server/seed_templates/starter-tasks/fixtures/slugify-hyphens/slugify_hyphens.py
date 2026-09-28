"""Convert free text into a URL-friendly slug."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Lowercase ``text``, replace runs of non-alphanumerics with one hyphen,
    and strip any leading or trailing hyphen."""
    lowered = text.lower()
    # BUG: replaces every non-alphanumeric character with its own hyphen
    # instead of collapsing consecutive runs into one, and never strips
    # the leading/trailing hyphens that result.
    return re.sub(r"[^a-z0-9]", "-", lowered)
