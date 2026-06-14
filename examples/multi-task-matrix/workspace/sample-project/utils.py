"""Utility helpers for the sample project."""

from __future__ import annotations


# Style issue: magic number not extracted to constant
_RAW_MAX = 255.0


def normalize(value: float) -> float:
    """Normalize a raw sensor value (0-255) to the range [0.0, 1.0]."""
    if value < 0:
        value = 0.0
    if value > _RAW_MAX:
        value = _RAW_MAX
    return value / _RAW_MAX


def clamp(value: float, low: float, high: float) -> float:
    """Clamp a value to [low, high]."""
    if low > high:
        raise ValueError(f"clamp: low ({low}) must be <= high ({high})")
    return max(low, min(high, value))


def percent(value: float) -> str:
    """Format a fraction as a percentage string."""
    return f"{value * 100:.1f}%"
