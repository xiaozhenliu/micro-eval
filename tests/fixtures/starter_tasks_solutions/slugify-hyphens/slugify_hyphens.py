"""Convert free text into a URL-friendly slug."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Lowercase ``text``, replace runs of non-alphanumerics with one hyphen,
    and strip any leading or trailing hyphen."""
    lowered = text.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered)
    return collapsed.strip("-")
