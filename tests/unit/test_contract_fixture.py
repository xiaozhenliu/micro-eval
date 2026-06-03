"""Shared Python/TypeScript contract fixture coverage."""

from __future__ import annotations

from pathlib import Path

from micro_eval.models.run import RunRecord


def test_shared_canonical_run_fixture_matches_pydantic_contract() -> None:
    fixture = Path("ui/src/lib/fixtures/canonical-run-p0.json")
    record = RunRecord.model_validate_json(fixture.read_text())

    assert record.id == "run-contract-fixture"
    assert record.same_start_snapshot is not None
    assert record.replay_canonical is not None
    assert record.results[0].cell_snapshot is not None
    assert record.results[0].snapshot_gate_result is not None
