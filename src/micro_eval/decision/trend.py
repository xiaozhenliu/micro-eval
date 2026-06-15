"""Cross-run trend analysis with drift-aware breakpoints.

Produces trend series for configurations across runs, marking breakpoints
where configuration content changed (#2 drift detection) so the trend line
doesn't misleadingly connect incomparable data points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from micro_eval.store.sqlite_store import SqliteStore


@dataclass
class TrendPoint:
    """One point in a trend series."""

    run_id: str
    created_at: str
    value: float | None
    verdict: str | None
    confidence: str | None
    drift_break: bool = False


@dataclass
class TrendSeries:
    """Complete trend for one configuration on one metric."""

    configuration_id: str
    metric: str
    points: list[TrendPoint] = field(default_factory=list)
    drift_count: int = 0


def compute_trend(
    project_root: Path | str,
    configuration_id: str,
    *,
    metric: str = "pass_rate",
    limit: int = 50,
) -> TrendSeries:
    """Compute a trend series for a configuration, with drift breakpoints."""
    store = SqliteStore(project_root)
    try:
        raw = store.trend_series(configuration_id, metric=metric, limit=limit)
    finally:
        store.close()

    points = [
        TrendPoint(
            run_id=item["run_id"],
            created_at=item["created_at"],
            value=item["value"],
            verdict=item["verdict"],
            confidence=item["confidence"],
            drift_break=item.get("drift_break", False),
        )
        for item in raw
    ]
    drift_count = sum(1 for p in points if p.drift_break)
    return TrendSeries(
        configuration_id=configuration_id,
        metric=metric,
        points=points,
        drift_count=drift_count,
    )


def compute_all_trends(
    project_root: Path | str,
    *,
    metric: str = "pass_rate",
    limit: int = 50,
) -> list[TrendSeries]:
    """Compute trend series for all known configurations."""
    store = SqliteStore(project_root)
    try:
        config_ids = store.configuration_ids()
        trends = []
        for config_id in config_ids:
            raw = store.trend_series(config_id, metric=metric, limit=limit)
            points = [
                TrendPoint(
                    run_id=item["run_id"],
                    created_at=item["created_at"],
                    value=item["value"],
                    verdict=item["verdict"],
                    confidence=item["confidence"],
                    drift_break=item.get("drift_break", False),
                )
                for item in raw
            ]
            drift_count = sum(1 for p in points if p.drift_break)
            trends.append(TrendSeries(
                configuration_id=config_id,
                metric=metric,
                points=points,
                drift_count=drift_count,
            ))
        return trends
    finally:
        store.close()
