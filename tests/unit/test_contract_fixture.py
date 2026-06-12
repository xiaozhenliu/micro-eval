"""Shared Python/TypeScript contract fixture coverage."""

from __future__ import annotations

from pathlib import Path

from micro_eval.models.decision import DecisionReport
from micro_eval.models.run import RunRecord


def test_shared_canonical_run_fixture_matches_pydantic_contract() -> None:
    fixture = Path("ui/src/lib/fixtures/canonical-run-p0.json")
    record = RunRecord.model_validate_json(fixture.read_text())

    assert record.id == "run-contract-fixture"
    assert record.same_start_snapshot is not None
    assert record.replay_canonical is not None
    assert record.results[0].cell_snapshot is not None
    assert record.results[0].snapshot_gate_result is not None


def test_shared_phase2_run_fixture_matches_pydantic_contract() -> None:
    # Guards the Phase 2 fixture consumed by ui api-route-contract tests:
    # if Pydantic models evolve, this fails before the TS side goes stale.
    record = RunRecord.model_validate_json(Path("ui/src/lib/fixtures/canonical-run-phase2.json").read_text())

    assert record.id == "run-phase2-fixture"
    assert record.traces and record.traces[0].provider in {"process", "langfuse"}
    assert any(item.evaluator_type == "llm_judge" for item in record.evaluations)
    assert record.decision is not None
    assert record.decision.decision_report_id
    assert all(stats.denominator_policy for stats in record.decision.aggregation.per_configuration.values())


def test_shared_phase2_decision_fixture_matches_pydantic_contract() -> None:
    report = DecisionReport.model_validate_json(Path("ui/src/lib/fixtures/canonical-decision-phase2.json").read_text())
    assert report.decision_report_id
    assert report.aggregation.per_configuration
