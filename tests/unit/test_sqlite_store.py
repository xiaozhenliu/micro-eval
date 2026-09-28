"""SQLite store and trend analysis tests (P3-e acceptance).

Verifies:
  - SqliteStore can index a RunRecord and query it back.
  - JSON runs can be imported into SQLite.
  - Trend series returns time-ordered points with drift breakpoints.
  - Configuration drift is marked correctly in trend data.
  - Legacy JSON compatibility is preserved (JSON remains source of truth).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from micro_eval.decision.aggregation import build_aggregation
from micro_eval.decision.summary import build_decision
from micro_eval.decision.trend import TrendSeries, compute_trend
from micro_eval.models.run import CellResult, CellStatus, RunRecord, RunStatus
from micro_eval.store.sqlite_store import SqliteStore


def _make_run(
    run_id: str,
    config_id: str = "cfg-a",
    created_at: str = "2026-06-14T00:00:00Z",
    pass_rate: float | None = 0.8,
    config_hash: str = "hash1",
) -> RunRecord:
    results = [
        CellResult(
            cell_id=f"{run_id}::task1::{config_id}::1",
            run_id=run_id,
            task_id="task1",
            configuration_id=config_id,
            configuration_name=config_id,
            repetition=1,
            status=CellStatus.passed,
            score=1.0,
            pass_fail="pass",
        ),
    ]
    record = RunRecord(
        id=run_id,
        project_name="test",
        status=RunStatus.completed,
        created_at=created_at,
        completed_at=created_at,
        output_dir=".micro-eval/runs",
        config_hash=config_hash,
        tasks=["task1"],
        configurations=[config_id],
        cells=[results[0].cell_id],
        results=results,
    )
    record.decision = build_decision(record)
    return record


class TestSqliteStore:
    def test_index_and_query(self, tmp_path: Path) -> None:
        store = SqliteStore(tmp_path)
        record = _make_run("run-001")
        store.index_run(record)
        series = store.trend_series("cfg-a")
        assert len(series) == 1
        assert series[0]["run_id"] == "run-001"
        store.close()

    def test_multiple_runs_ordered_by_time(self, tmp_path: Path) -> None:
        store = SqliteStore(tmp_path)
        store.index_run(_make_run("run-001", created_at="2026-06-14T01:00:00Z"))
        store.index_run(_make_run("run-002", created_at="2026-06-14T02:00:00Z"))
        store.index_run(_make_run("run-003", created_at="2026-06-14T03:00:00Z"))
        series = store.trend_series("cfg-a")
        assert [p["run_id"] for p in series] == ["run-001", "run-002", "run-003"]
        store.close()

    def test_drift_break_on_config_hash_change(self, tmp_path: Path) -> None:
        store = SqliteStore(tmp_path)
        store.index_run(_make_run("run-001", created_at="2026-06-14T01:00:00Z", config_hash="h1"))
        store.index_run(_make_run("run-002", created_at="2026-06-14T02:00:00Z", config_hash="h2"))
        store.index_run(_make_run("run-003", created_at="2026-06-14T03:00:00Z", config_hash="h2"))
        series = store.trend_series("cfg-a")
        assert series[0]["drift_break"] is False
        assert series[1]["drift_break"] is True
        assert series[2]["drift_break"] is False
        store.close()

    def test_configuration_ids(self, tmp_path: Path) -> None:
        store = SqliteStore(tmp_path)
        store.index_run(_make_run("run-001", config_id="alpha"))
        store.index_run(_make_run("run-002", config_id="beta"))
        ids = store.configuration_ids()
        assert "alpha" in ids
        assert "beta" in ids
        store.close()

    def test_import_json_runs(self, tmp_path: Path) -> None:
        runs_dir = tmp_path / ".micro-eval" / "runs"
        run_dir = runs_dir / "run-import-test"
        run_dir.mkdir(parents=True)
        record = _make_run("run-import-test")
        (run_dir / "run.json").write_text(record.model_dump_json(indent=2))
        if record.decision:
            (run_dir / "decision.json").write_text(record.decision.model_dump_json(indent=2))

        store = SqliteStore(tmp_path)
        count = store.import_json_runs()
        assert count == 1
        series = store.trend_series("cfg-a")
        assert len(series) == 1
        store.close()


class TestComputeTrend:
    def test_compute_trend_returns_series(self, tmp_path: Path) -> None:
        store = SqliteStore(tmp_path)
        store.index_run(_make_run("run-001", created_at="2026-06-14T01:00:00Z"))
        store.index_run(_make_run("run-002", created_at="2026-06-14T02:00:00Z"))
        store.close()

        trend = compute_trend(tmp_path, "cfg-a")
        assert isinstance(trend, TrendSeries)
        assert len(trend.points) == 2
        assert trend.configuration_id == "cfg-a"

    def test_drift_count_is_correct(self, tmp_path: Path) -> None:
        store = SqliteStore(tmp_path)
        store.index_run(_make_run("run-001", created_at="2026-06-14T01:00:00Z", config_hash="h1"))
        store.index_run(_make_run("run-002", created_at="2026-06-14T02:00:00Z", config_hash="h2"))
        store.index_run(_make_run("run-003", created_at="2026-06-14T03:00:00Z", config_hash="h3"))
        store.close()

        trend = compute_trend(tmp_path, "cfg-a")
        assert trend.drift_count == 2
