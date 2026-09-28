"""Comparative decision contract coverage."""

from __future__ import annotations

import pytest

from micro_eval.decision.summary import build_decision
from micro_eval.models.configuration import EvaluationContract
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.run import CellResult, CellStatus, RunRecord, RunStatus


def _record(
    outcomes: dict[tuple[str, str], list[str | None]],
    *,
    threshold: float | None = 0.5,
    policy: str = "include_failed",
    min_repetitions: int = 1,
    evaluators: list[str] | None = None,
    roles: dict[str, str | None] | None = None,
) -> RunRecord:
    results: list[CellResult] = []
    evaluations: list[EvaluationResult] = []
    for (task_id, config_id), values in outcomes.items():
        for repetition, outcome in enumerate(values, 1):
            cell_id = f"{task_id}-{config_id}-{repetition}"
            status = CellStatus.passed if outcome == "pass" else CellStatus.failed if outcome == "fail" else CellStatus.error
            eval_refs: list[str] = []
            evidence_refs = [f"{cell_id}::evidence"]
            artifact_refs = [f"{cell_id}::stdout"]
            if outcome in {"pass", "fail"}:
                eval_id = f"{cell_id}::validator"
                eval_refs = [eval_id]
                evaluations.append(EvaluationResult(
                    evaluation_id=eval_id,
                    cell_id=cell_id,
                    pass_fail=outcome,
                    evidence_refs=evidence_refs,
                ))
            results.append(CellResult(
                cell_id=cell_id,
                run_id="run-comparison",
                task_id=task_id,
                configuration_id=config_id,
                configuration_name=config_id,
                repetition=repetition,
                status=status,
                pass_fail=outcome if outcome in {"pass", "fail"} else None,
                evaluation_refs=eval_refs,
                evidence_refs=evidence_refs,
                artifact_refs=artifact_refs,
            ))
    return RunRecord(
        id="run-comparison",
        project_name="comparison",
        status=RunStatus.completed,
        created_at="2026-08-29T00:00:00Z",
        output_dir=".micro-eval/runs",
        tasks=sorted({task for task, _ in outcomes}),
        configurations=["baseline", "candidate"],
        cells=[result.cell_id for result in results],
        results=results,
        evaluations=evaluations,
        configuration_roles=roles or {"baseline": "baseline", "candidate": "candidate"},
        evaluation_contract=EvaluationContract(
            decision_threshold=threshold,
            denominator_policy=policy,  # type: ignore[arg-type]
            min_repetitions=min_repetitions,
            required_evaluators=evaluators or ["validator"],
        ),
    )


def test_task_comparison_emits_regressed_with_low_sample_and_refs() -> None:
    record = _record({
        ("stable", "baseline"): ["pass", "pass"],
        ("stable", "candidate"): ["pass", "pass"],
        ("broken", "baseline"): ["pass", "pass"],
        ("broken", "candidate"): ["fail", "fail"],
    })
    decision = build_decision(record)
    assert decision.verdict.value == "regressed"
    assert decision.comparison is not None
    assert decision.comparison.candidate_configuration_id == "candidate"
    broken = next(item for item in decision.comparison.tasks if item.task_id == "broken")
    assert broken.direction == "regressed"
    assert broken.delta == -1.0
    assert broken.cell_refs and broken.evaluation_refs and broken.evidence_refs
    assert "low_sample" in broken.caveats
    assert decision.confidence == "low"


def test_mixed_and_all_unchanged_are_safely_synthesized() -> None:
    mixed = _record({
        ("up", "baseline"): ["fail", "fail"], ("up", "candidate"): ["pass", "pass"],
        ("down", "baseline"): ["pass", "pass"], ("down", "candidate"): ["fail", "fail"],
    })
    assert build_decision(mixed).verdict.value == "mixed"
    unchanged = _record({
        ("same", "baseline"): ["pass", "pass"], ("same", "candidate"): ["pass", "pass"],
    })
    decision = build_decision(unchanged)
    assert decision.verdict.value == "inconclusive"
    assert "decision_threshold_not_set" not in decision.caveats
    assert "threshold" in decision.recommended_action


def test_missing_threshold_and_unsupported_evaluator_are_protected() -> None:
    no_threshold = _record({("task", "baseline"): ["pass"], ("task", "candidate"): ["fail"]}, threshold=None)
    decision = build_decision(no_threshold)
    assert decision.verdict.value == "inconclusive"
    assert "decision_threshold_not_set" in decision.caveats
    human = _record({("task", "baseline"): ["pass"], ("task", "candidate"): ["fail"]}, evaluators=["validator", "human"])
    decision = build_decision(human)
    assert decision.verdict.value == "needs_human_review"
    assert "unsupported_evaluator_contract" in decision.caveats


def test_missing_contract_never_guesses_roles() -> None:
    record = _record({("task", "baseline"): ["pass"], ("task", "candidate"): ["fail"]})
    record.evaluation_contract = None
    record.configuration_roles = {}
    decision = build_decision(record)
    assert decision.verdict.value == "inconclusive"
    assert "comparison_contract_unavailable" in decision.caveats


def test_error_is_counted_or_excluded_by_denominator_policy() -> None:
    outcomes = {
        ("task", "baseline"): ["pass", "pass"],
        ("task", "candidate"): ["pass", None],
    }
    include = build_decision(_record(outcomes, policy="include_failed"))
    assert include.verdict.value == "regressed"
    assert "execution_failure_counted:task" in include.caveats
    exclude = build_decision(_record(outcomes, policy="exclude_failed"))
    assert exclude.verdict.value == "inconclusive"
    assert exclude.comparison is not None
    assert exclude.comparison.tasks[0].candidate_sample_count == 1


def test_threshold_validation_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="decision_threshold"):
        EvaluationContract(decision_threshold=0)
    with pytest.raises(ValueError, match="decision_threshold"):
        EvaluationContract(decision_threshold=1.01)
