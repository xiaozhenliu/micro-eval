"""Tiny ledger allocation module used by the micro-eval example."""

from __future__ import annotations


def split_amount_cents(total_cents: int, weights: list[int]) -> list[int]:
    """Split total cents across positive integer weights.

    The implementation is intentionally buggy for the example: it floors each
    share and drops leftover cents instead of distributing the remainder.
    """
    if total_cents < 0:
        raise ValueError("total_cents must be non-negative")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(weight <= 0 for weight in weights):
        raise ValueError("weights must be positive")

    total_weight = sum(weights)
    return [(total_cents * weight) // total_weight for weight in weights]
