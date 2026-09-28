"""Decision report persistence and compatibility coverage."""

from __future__ import annotations

import json
from pathlib import Path

from micro_eval.models.decision import DecisionReport, DecisionStatus
from micro_eval.models.run import RunRecord, RunStatus
from micro_eval.store.run_store import RunStore


def _record() -> RunRecord:
    return RunRecord(
        id="run-store-test",
        project_name="store-test",
        status=RunStatus.completed,
        created_at="2026-06-12T10:30:00+00:00",
        output_dir=".micro-eval/runs",
        decision=DecisionReport(
            decision_report_id="run-store-test::decision::20260612T103000Z",
            verdict=DecisionStatus.inconclusive,
            confidence="low",
            timestamp="20260612T103000Z",
        ),
    )


def test_run_store_writes_and_prefers_decision_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    record = _record()

    store.write_run(record)
    decision_path = tmp_path / ".micro-eval" / "runs" / record.id / "decision.json"
    assert decision_path.exists()

    raw = json.loads(decision_path.read_text())
    raw["verdict"] = "not_comparable"
    decision_path.write_text(json.dumps(raw))

    loaded = store.read_run(record.id)

    assert loaded.decision is not None
    assert loaded.decision.verdict == DecisionStatus.not_comparable
    assert loaded.decision.decision_report_id == "run-store-test::decision::20260612T103000Z"


def test_run_store_falls_back_to_legacy_embedded_decision(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    record = _record()
    run_dir = store.run_dir(record.id, record.output_dir)
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(record.model_dump_json(indent=2))

    loaded = store.read_run(record.id)

    assert loaded.decision is not None
    assert loaded.decision.verdict == DecisionStatus.inconclusive
