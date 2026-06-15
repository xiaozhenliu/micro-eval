"""Coverage tests for decision/trend.py — compute_trend and compute_all_trends."""

from __future__ import annotations

from pathlib import Path

import pytest

from micro_eval.decision.trend import TrendPoint, TrendSeries, compute_all_trends, compute_trend
from micro_eval.models.decision import AggregationResult, ConfigurationStats, DecisionReport, DecisionStatus
from micro_eval.models.run import RunRecord, RunStatus
from micro_eval.store.sqlite_store import SqliteStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    run_id: str,
    *,
    created_at: str,
    config_hash: str = "abc123",
    pass_rate: float | None = None,
    verdict: str = "inconclusive",
    config_ids: list[str] | None = None,
) -> RunRecord:
    """Build a minimal RunRecord with optional per-configuration stats."""
    per_cfg: dict[str, ConfigurationStats] = {}
    for cid in (config_ids or []):
        per_cfg[cid] = ConfigurationStats(
            n_cells=3,
            n_successful=3,
            pass_rate=pass_rate,
        )

    decision = DecisionReport(
        decision_report_id=f"{run_id}::decision",
        verdict=DecisionStatus(verdict),
        confidence="low",
        timestamp=created_at,
        aggregation=AggregationResult(per_configuration=per_cfg),
    )

    return RunRecord(
        id=run_id,
        project_name="test-project",
        status=RunStatus.completed,
        created_at=created_at,
        output_dir=".micro-eval/runs",
        config_hash=config_hash,
        decision=decision,
    )


def _index(store: SqliteStore, record: RunRecord) -> None:
    store.index_run(record, json_path=f".micro-eval/runs/{record.id}/run.json")


# ---------------------------------------------------------------------------
# compute_trend — single configuration
# ---------------------------------------------------------------------------


def test_compute_trend_returns_empty_for_unknown_configuration(tmp_path: Path) -> None:
    series = compute_trend(tmp_path, "no-such-config")

    assert isinstance(series, TrendSeries)
    assert series.configuration_id == "no-such-config"
    assert series.metric == "pass_rate"
    assert series.points == []
    assert series.drift_count == 0


def test_compute_trend_single_point_no_division_error(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    record = _make_record(
        "run-001",
        created_at="2026-06-01T10:00:00+00:00",
        pass_rate=1.0,
        config_ids=["cfg-a"],
    )
    _index(store, record)
    store.close()

    series = compute_trend(tmp_path, "cfg-a")

    assert len(series.points) == 1
    point = series.points[0]
    assert point.run_id == "run-001"
    assert point.value == pytest.approx(1.0)
    assert point.drift_break is False
    assert series.drift_count == 0


def test_compute_trend_multiple_points_no_drift(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    for i, (run_id, ts, pr) in enumerate([
        ("run-001", "2026-06-01T10:00:00+00:00", 0.5),
        ("run-002", "2026-06-02T10:00:00+00:00", 0.7),
        ("run-003", "2026-06-03T10:00:00+00:00", 0.9),
    ]):
        record = _make_record(
            run_id,
            created_at=ts,
            config_hash="same-hash",
            pass_rate=pr,
            config_ids=["cfg-stable"],
        )
        _index(store, record)
    store.close()

    series = compute_trend(tmp_path, "cfg-stable")

    assert len(series.points) == 3
    assert series.drift_count == 0
    assert all(not p.drift_break for p in series.points)
    assert [p.value for p in series.points] == pytest.approx([0.5, 0.7, 0.9])


def test_compute_trend_drift_breakpoint_on_hash_change(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    runs = [
        ("run-001", "2026-06-01T10:00:00+00:00", "hash-v1", 0.6),
        ("run-002", "2026-06-02T10:00:00+00:00", "hash-v1", 0.65),
        ("run-003", "2026-06-03T10:00:00+00:00", "hash-v2", 0.4),  # hash changed -> breakpoint
        ("run-004", "2026-06-04T10:00:00+00:00", "hash-v2", 0.5),
    ]
    for run_id, ts, chash, pr in runs:
        record = _make_record(
            run_id,
            created_at=ts,
            config_hash=chash,
            pass_rate=pr,
            config_ids=["cfg-drift"],
        )
        _index(store, record)
    store.close()

    series = compute_trend(tmp_path, "cfg-drift")

    assert len(series.points) == 4
    assert series.points[0].drift_break is False
    assert series.points[1].drift_break is False
    # Third point is where hash changed
    assert series.points[2].drift_break is True
    assert series.points[3].drift_break is False
    assert series.drift_count == 1


def test_compute_trend_passes_metric_kwarg(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    stats = ConfigurationStats(n_cells=2, n_successful=2, mean_latency_ms=120.0, pass_rate=1.0)
    decision = DecisionReport(
        decision_report_id="run-lat::decision",
        verdict=DecisionStatus.inconclusive,
        confidence="low",
        timestamp="2026-06-01T10:00:00+00:00",
        aggregation=AggregationResult(per_configuration={"cfg-lat": stats}),
    )
    record = RunRecord(
        id="run-lat",
        project_name="test",
        status=RunStatus.completed,
        created_at="2026-06-01T10:00:00+00:00",
        output_dir=".micro-eval/runs",
        config_hash="h1",
        decision=decision,
    )
    _index(store, record)
    store.close()

    series = compute_trend(tmp_path, "cfg-lat", metric="mean_latency_ms")

    assert series.metric == "mean_latency_ms"
    assert len(series.points) == 1
    assert series.points[0].value == pytest.approx(120.0)


def test_compute_trend_respects_limit(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    for i in range(10):
        record = _make_record(
            f"run-{i:03d}",
            created_at=f"2026-06-{i+1:02d}T10:00:00+00:00",
            config_hash="stable",
            pass_rate=float(i) / 10,
            config_ids=["cfg-many"],
        )
        _index(store, record)
    store.close()

    series = compute_trend(tmp_path, "cfg-many", limit=3)

    assert len(series.points) == 3


# ---------------------------------------------------------------------------
# compute_all_trends
# ---------------------------------------------------------------------------


def test_compute_all_trends_empty_store_returns_empty_list(tmp_path: Path) -> None:
    result = compute_all_trends(tmp_path)

    assert result == []


def test_compute_all_trends_single_configuration(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    record = _make_record(
        "run-001",
        created_at="2026-06-01T10:00:00+00:00",
        pass_rate=0.8,
        config_ids=["cfg-solo"],
    )
    _index(store, record)
    store.close()

    result = compute_all_trends(tmp_path)

    assert len(result) == 1
    assert result[0].configuration_id == "cfg-solo"
    assert len(result[0].points) == 1
    assert result[0].points[0].value == pytest.approx(0.8)


def test_compute_all_trends_multiple_configurations(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    for i, cid in enumerate(["cfg-a", "cfg-b", "cfg-c"]):
        record = _make_record(
            f"run-{cid}",
            created_at=f"2026-06-{i+1:02d}T10:00:00+00:00",
            pass_rate=0.5 + i * 0.1,
            config_ids=[cid],
        )
        _index(store, record)
    store.close()

    result = compute_all_trends(tmp_path)

    assert len(result) == 3
    config_ids = {s.configuration_id for s in result}
    assert config_ids == {"cfg-a", "cfg-b", "cfg-c"}
    for series in result:
        assert len(series.points) == 1
        assert series.drift_count == 0


def test_compute_all_trends_multi_run_per_config_with_drift(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    # cfg-x: two runs, no drift
    for i, (ts, pr) in enumerate([
        ("2026-06-01T10:00:00+00:00", 0.6),
        ("2026-06-02T10:00:00+00:00", 0.7),
    ]):
        record = _make_record(
            f"run-x-{i}",
            created_at=ts,
            config_hash="hash-x",
            pass_rate=pr,
            config_ids=["cfg-x"],
        )
        _index(store, record)

    # cfg-y: two runs, drift on second run
    for i, (ts, chash, pr) in enumerate([
        ("2026-06-01T10:00:00+00:00", "hash-y1", 0.9),
        ("2026-06-02T10:00:00+00:00", "hash-y2", 0.3),
    ]):
        record = _make_record(
            f"run-y-{i}",
            created_at=ts,
            config_hash=chash,
            pass_rate=pr,
            config_ids=["cfg-y"],
        )
        _index(store, record)
    store.close()

    result = compute_all_trends(tmp_path)

    by_id = {s.configuration_id: s for s in result}
    assert set(by_id.keys()) == {"cfg-x", "cfg-y"}

    x = by_id["cfg-x"]
    assert x.drift_count == 0
    assert all(not p.drift_break for p in x.points)

    y = by_id["cfg-y"]
    assert y.drift_count == 1
    assert y.points[1].drift_break is True


def test_compute_all_trends_uses_metric_kwarg(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path)
    stats = ConfigurationStats(n_cells=1, n_successful=1, mean_latency_ms=250.0, pass_rate=1.0)
    decision = DecisionReport(
        decision_report_id="run-mt::decision",
        verdict=DecisionStatus.inconclusive,
        confidence="low",
        timestamp="2026-06-01T10:00:00+00:00",
        aggregation=AggregationResult(per_configuration={"cfg-mt": stats}),
    )
    record = RunRecord(
        id="run-mt",
        project_name="test",
        status=RunStatus.completed,
        created_at="2026-06-01T10:00:00+00:00",
        output_dir=".micro-eval/runs",
        config_hash="h1",
        decision=decision,
    )
    _index(store, record)
    store.close()

    result = compute_all_trends(tmp_path, metric="mean_latency_ms")

    assert len(result) == 1
    series = result[0]
    assert series.metric == "mean_latency_ms"
    assert series.points[0].value == pytest.approx(250.0)
