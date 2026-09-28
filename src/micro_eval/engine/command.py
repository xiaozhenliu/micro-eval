"""Shared argv placeholder resolution for trusted subprocess entry points."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence


def resolve_command_argv(
    command: Sequence[str],
    *,
    replacements: Mapping[str, str] | None = None,
) -> list[str]:
    """Resolve supported placeholders without invoking a shell."""
    values = {"{python}": sys.executable}
    if replacements:
        values.update(replacements)

    argv: list[str] = []
    for arg in command:
        value = arg
        for placeholder, replacement in values.items():
            value = value.replace(placeholder, replacement)
        argv.append(value)
    return argv
