"""Phase 2 aggregation acceptance coverage."""

from __future__ import annotations

import pytest

from micro_eval.decision.aggregation import aggregate_configuration
from micro_eval.models.run import CellResult, CellStatus


def _cell(cell_id: str, *, status: CellStatus, pass_fail: str | None, latency_s: float = 1.0) -> CellResult:
    return CellResult(
        cell_id=cell_id,
        run_id="run-aggregation",
        task_id="task",
        configuration_id="cfg",
        configuration_name="cfg",
        repetition=1,
        status=status,
        pass_fail=pass_fail,
        latency_s=latency_s,
        evidence_refs=[f"{cell_id}::evidence"],
        evaluation_refs=[f"{cell_id}::eval"],
    )


def test_binary_pass_at_k_and_pass_hat_k_are_computed() -> None:
    stats = aggregate_configuration(
        [
            _cell("cell-1", status=CellStatus.passed, pass_fail="pass"),
            _cell("cell-2", status=CellStatus.failed, pass_fail="fail"),
            _cell("cell-3", status=CellStatus.passed, pass_fail="pass"),
        ]
    )

    assert stats.pass_rate == 2 / 3
    assert stats.pass_at_k == pytest.approx({1: 2 / 3, 2: 1.0, 3: 1.0})
    assert stats.pass_hat_k is not None
    assert stats.pass_hat_k[2] == (2 / 3) ** 2
    assert stats.caveats == []


def test_non_binary_missing_results_do_not_get_pass_at_k() -> None:
    stats = aggregate_configuration(
        [
            _cell("cell-1", status=CellStatus.error, pass_fail=None),
            _cell("cell-2", status=CellStatus.timeout, pass_fail=None),
        ]
    )

    assert stats.pass_rate is None
    assert stats.pass_at_k is None
    assert stats.pass_hat_k is None


def test_denominator_policy_controls_failed_or_missing_cells() -> None:
    results = [
        _cell("cell-1", status=CellStatus.passed, pass_fail="pass"),
        _cell("cell-2", status=CellStatus.error, pass_fail=None),
    ]

    include_failed = aggregate_configuration(results, denominator_policy="include_failed")
    exclude_failed = aggregate_configuration(results, denominator_policy="exclude_failed")

    assert include_failed.pass_rate == 0.5
    assert include_failed.denominator_policy == "include_failed"
    assert exclude_failed.pass_rate == 1.0
    assert exclude_failed.denominator_policy == "exclude_failed"


def test_low_sample_caveat_and_repetition_one_identity() -> None:
    stats = aggregate_configuration([_cell("cell-1", status=CellStatus.passed, pass_fail="pass")])

    assert stats.pass_rate == 1.0
    assert stats.pass_at_k == {1: stats.pass_rate}
    assert stats.pass_hat_k == {1: stats.pass_rate}
    assert "low_sample" in stats.caveats
