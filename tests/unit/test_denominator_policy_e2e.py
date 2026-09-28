"""End-to-end tests verifying denominator_policy flows from RunRecord into build_decision."""

from __future__ import annotations

from micro_eval.decision.summary import build_decision
from micro_eval.models.run import CellResult, CellStatus, RunRecord, RunStatus


def _record(policy: str, results: list[CellResult]) -> RunRecord:
    return RunRecord(
        id="run-policy-test",
        project_name="test",
        status=RunStatus.completed,
        created_at="2026-06-12T00:00:00+00:00",
        output_dir=".micro-eval/runs",
        cells=[r.cell_id for r in results],
        configurations=sorted({r.configuration_id for r in results}),
        results=results,
        denominator_policy=policy,  # type: ignore[arg-type]
        evidence=[],
        evaluations=[],
    )


def _cell(cell_id: str, cfg: str, *, status: CellStatus, pass_fail: str | None) -> CellResult:
    return CellResult(
        cell_id=cell_id,
        run_id="run-policy-test",
        task_id="task",
        configuration_id=cfg,
        configuration_name=cfg,
        repetition=1,
        status=status,
        pass_fail=pass_fail,
    )


def test_exclude_failed_policy_uses_successful_cells_as_denominator() -> None:
    """exclude_failed: error cell excluded from denominator, pass_rate == 1.0 not 0.5."""
    results = [
        _cell("c1", "cfg-a", status=CellStatus.passed, pass_fail="pass"),
        _cell("c2", "cfg-a", status=CellStatus.error, pass_fail=None),
        _cell("c3", "cfg-a", status=CellStatus.passed, pass_fail="pass"),
        _cell("c4", "cfg-a", status=CellStatus.passed, pass_fail="pass"),
    ]
    record = _record("exclude_failed", results)
    decision = build_decision(record)
    stats = decision.aggregation.per_configuration["cfg-a"]

    assert stats.denominator_policy == "exclude_failed"
    # 3 passed out of 3 successful (error excluded) → 1.0
    assert stats.pass_rate == 1.0


def test_include_failed_policy_is_default_and_counts_all_cells() -> None:
    """include_failed: error cell counts as denominator, pass_rate == 0.75 not 1.0."""
    results = [
        _cell("c1", "cfg-b", status=CellStatus.passed, pass_fail="pass"),
        _cell("c2", "cfg-b", status=CellStatus.error, pass_fail=None),
        _cell("c3", "cfg-b", status=CellStatus.passed, pass_fail="pass"),
        _cell("c4", "cfg-b", status=CellStatus.passed, pass_fail="pass"),
    ]
    record = _record("include_failed", results)
    decision = build_decision(record)
    stats = decision.aggregation.per_configuration["cfg-b"]

    assert stats.denominator_policy == "include_failed"
    # 3 passed out of 4 total cells → 0.75
    assert stats.pass_rate == 0.75
