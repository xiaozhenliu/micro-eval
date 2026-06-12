"""Workspace-boundary and legacy-compatibility tests for RunStore."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from micro_eval.models.run import RunRecord
from micro_eval.store.run_store import RunStore, RunStoreError


def _record(run_id: str, created_at: str) -> RunRecord:
    return RunRecord(id=run_id, project_name="proj", created_at=created_at, output_dir=".micro-eval/runs")


def test_run_dir_rejects_output_dir_escaping_project_root(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    with pytest.raises(RunStoreError):
        store.run_dir("run-1", "../outside")


def test_list_runs_includes_legacy_flat_json_and_skips_broken_files(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.write_run(_record("run-new", "2026-06-12T10:00:00Z"))
    runs_dir = tmp_path / ".micro-eval/runs"
    (runs_dir / "legacy.json").write_text(json.dumps({"id": "run-legacy", "timestamp": "2026-06-11T09:00:00Z"}))
    (runs_dir / "broken.json").write_text("{not json")

    runs = store.list_runs()
    ids = [run.id if isinstance(run, RunRecord) else run["id"] for run in runs]
    assert ids == ["run-new", "run-legacy"]


def test_latest_run_id(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    assert store.latest_run_id() is None
    store.write_run(_record("run-old", "2026-06-10T08:00:00Z"))
    store.write_run(_record("run-new", "2026-06-12T08:00:00Z"))
    assert store.latest_run_id() == "run-new"
