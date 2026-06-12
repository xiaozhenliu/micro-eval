"""Trace provider protocol and fallback collection helpers."""

from __future__ import annotations

from typing import Protocol

from micro_eval.engine.adapter import Redactor
from micro_eval.models.artifact import TraceRef
from micro_eval.models.run import AdapterResult, RunCell


class TraceProvider(Protocol):
    """Collect a normalized trace reference after one cell execution."""

    name: str

    def collect(self, cell: RunCell, result: AdapterResult, redactor: Redactor) -> TraceRef | None:
        """Collect trace metadata, returning None when unavailable."""
        ...


def collect_trace_with_fallback(
    providers: list[TraceProvider],
    *,
    cell: RunCell,
    result: AdapterResult,
    redactor: Redactor,
) -> TraceRef | None:
    """Try providers in order; never let optional trace collection fail the run."""
    warnings: list[str] = []
    for provider in providers:
        try:
            trace = provider.collect(cell, result, redactor)
        except Exception as exc:  # noqa: BLE001 - optional provider failures must downgrade.
            warnings.append(f"{provider.name}: {exc.__class__.__name__}")
            continue
        if trace is None:
            continue
        if warnings:
            summary = dict(trace.summary or {})
            summary["fallback_warnings"] = redactor.redact("; ".join(warnings))[:500]
            trace.summary = summary
        return trace
    return None
