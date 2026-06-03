"""P0-b decision guardrail coverage."""

from __future__ import annotations

from micro_eval.decision.summary import build_decision
from micro_eval.models.environment import CellSnapshot, SnapshotGateResult
from micro_eval.models.run import CellResult, CellStatus, RunRecord, RunStatus


def test_snapshot_gate_warning_downgrades_decision_to_not_comparable() -> None:
    record = RunRecord(
        id="run-test",
        project_name="test",
        status=RunStatus.completed,
        created_at="2026-06-02T00:00:00+00:00",
        output_dir=".micro-eval/runs",
        cells=["cell-1"],
        configurations=["baseline", "candidate"],
        results=[
            CellResult(
                cell_id="cell-1",
                run_id="run-test",
                task_id="task",
                configuration_id="baseline",
                configuration_name="baseline",
                repetition=1,
                status=CellStatus.passed,
                pass_fail="pass",
                evidence_refs=["evidence-1"],
                evaluation_refs=["eval-1"],
                cell_snapshot=CellSnapshot(workspace_path="/tmp/a", timestamp="now"),
                snapshot_gate_result=SnapshotGateResult(status="warn", mismatch_fields=["git_commit"]),
            )
        ],
    )

    decision = build_decision(record)

    assert decision.verdict.value == "not_comparable"
    assert any("snapshot gate warning" in caveat for caveat in decision.caveats)
