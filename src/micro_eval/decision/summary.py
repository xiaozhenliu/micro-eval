"""Guarded, auditable baseline/candidate decision summaries."""

from __future__ import annotations

from micro_eval.decision.aggregation import build_aggregation
from micro_eval.models.decision import ComparisonResult, DecisionReport, DecisionStatus, TaskComparison
from micro_eval.models.ids import compact_timestamp
from micro_eval.models.run import CellResult, CellStatus, RunRecord, RunStatus


def build_decision(record: RunRecord) -> DecisionReport:
    """Build a decision using only facts persisted in the run artifact."""
    contract = record.evaluation_contract
    policy = contract.denominator_policy if contract is not None else record.denominator_policy
    aggregation = build_aggregation(record.results, traces=record.traces, denominator_policy=policy)
    all_eval_refs = _unique(ref for result in record.results for ref in result.evaluation_refs)
    all_evidence_refs = _unique(ref for result in record.results for ref in result.evidence_refs)
    caveats = list(record.migration_warnings)
    if record.same_start_snapshot:
        caveats.extend(record.same_start_snapshot.caveats)
    snapshot_mismatches = [
        result for result in record.results
        if result.snapshot_gate_result and result.snapshot_gate_result.status != "pass"
    ]
    for result in snapshot_mismatches:
        gate = result.snapshot_gate_result
        fields = ", ".join(gate.mismatch_fields) if gate else "snapshot gate"
        caveats.append(f"snapshot gate warning for {result.cell_id}: {fields or 'cleanup/caveat'}")

    roles = record.configuration_roles
    baseline_ids = [key for key, role in roles.items() if role == "baseline"]
    candidate_ids = [key for key, role in roles.items() if role == "candidate"]
    base_kwargs = dict(
        aggregation=aggregation,
        evaluation_refs=all_eval_refs,
        evidence_refs=all_evidence_refs,
        confidence="low",
    )

    # Protection precedence: comparability first.
    if snapshot_mismatches:
        return _report(record, DecisionStatus.not_comparable, "fix same-start snapshot mismatches before comparing configurations", caveats, **base_kwargs)

    if record.status == RunStatus.cancelled:
        caveats.append("run was cancelled; only completed cells were summarized")
        return _report(record, DecisionStatus.inconclusive, "review the completed cells; cancelled runs cannot establish a comparison", caveats, **base_kwargs)

    if len(baseline_ids) != 1 or len(candidate_ids) != 1 or set(baseline_ids + candidate_ids) != set(record.configurations):
        caveats.append("comparison_contract_unavailable" if contract is None else "configuration_roles_invalid")
        return _report(record, DecisionStatus.inconclusive, "record one baseline and one candidate role before comparing configurations", caveats, **base_kwargs)

    if contract is not None and set(contract.required_evaluators) != {"validator"}:
        caveats.append("unsupported_evaluator_contract")
        return _report(record, DecisionStatus.needs_human_review, "review non-validator evaluations before deciding", caveats, **base_kwargs)

    if contract is None:
        caveats.append("comparison_contract_unavailable")
        return _report(record, DecisionStatus.inconclusive, "recompute requires the persisted evaluation contract", caveats, **base_kwargs)

    if record.status != RunStatus.completed or len(record.results) < len(record.cells):
        caveats.append("run is partial; not all cells completed")
        return _report(record, DecisionStatus.inconclusive, "complete every planned cell before deciding", caveats, **base_kwargs)

    baseline_id, candidate_id = baseline_ids[0], candidate_ids[0]
    baseline_tasks = {r.task_id for r in record.results if r.configuration_id == baseline_id}
    candidate_tasks = {r.task_id for r in record.results if r.configuration_id == candidate_id}
    if baseline_tasks != candidate_tasks:
        caveats.append("task_set_mismatch")
        return _report(record, DecisionStatus.not_comparable, "align the task set on baseline and candidate before comparing", caveats, **base_kwargs)

    evaluations_by_id = {evaluation.evaluation_id: evaluation for evaluation in record.evaluations}
    comparisons: list[TaskComparison] = []
    for task_id in sorted(baseline_tasks):
        left = [r for r in record.results if r.configuration_id == baseline_id and r.task_id == task_id]
        right = [r for r in record.results if r.configuration_id == candidate_id and r.task_id == task_id]
        left_sample = _denominator(left, contract.denominator_policy)
        right_sample = _denominator(right, contract.denominator_policy)
        if len(left_sample) < contract.min_repetitions or len(right_sample) < contract.min_repetitions:
            caveats.append(f"min_repetitions_not_met:{task_id}")
        if any(not _auditable(result, evaluations_by_id) for result in left_sample + right_sample):
            caveats.append(f"machine_evidence_missing:{task_id}")
        task_caveats: list[str] = []
        if len(left_sample) < 3 or len(right_sample) < 3:
            task_caveats.append("low_sample")
            caveats.append(f"low sample size for {task_id}: repetitions < 3")
        if any(result.status in {CellStatus.error, CellStatus.timeout} for result in left_sample + right_sample):
            task_caveats.append("execution_failure_counted")
            caveats.append(f"execution_failure_counted:{task_id}")
        if not left_sample or not right_sample or any(not _auditable(result, evaluations_by_id) for result in left_sample + right_sample):
            continue
        left_rate = _pass_rate(left_sample)
        right_rate = _pass_rate(right_sample)
        delta = right_rate - left_rate
        direction = _direction(delta, contract.decision_threshold)
        if direction is None:
            caveats.append("decision_threshold_not_set")
            continue
        comparisons.append(TaskComparison(
            task_id=task_id,
            baseline_sample_count=len(left_sample),
            candidate_sample_count=len(right_sample),
            baseline_pass_rate=left_rate,
            candidate_pass_rate=right_rate,
            delta=delta,
            direction=direction,
            cell_refs=_unique(result.cell_id for result in left_sample + right_sample),
            evaluation_refs=_unique(ref for result in left_sample + right_sample for ref in result.evaluation_refs),
            evidence_refs=_unique(ref for result in left_sample + right_sample for ref in result.evidence_refs),
            artifact_refs=_unique(ref for result in left_sample + right_sample for ref in result.artifact_refs),
            trace_refs=_unique(ref for result in left_sample + right_sample for ref in result.trace_refs),
            caveats=task_caveats,
        ))

    if contract.decision_threshold is None:
        caveats.append("decision_threshold_not_set")
        return _report(record, DecisionStatus.inconclusive, "set decision_threshold before automatically deciding", caveats, **base_kwargs)
    if len(comparisons) != len(baseline_tasks):
        return _report(record, DecisionStatus.inconclusive, "complete auditable validator evidence and minimum repetitions before deciding", caveats, **base_kwargs)
    if any("min_repetitions_not_met:" in caveat for caveat in caveats):
        return _report(record, DecisionStatus.inconclusive, "meet min_repetitions on both sides of every task before deciding", caveats, **base_kwargs)
    if any("machine_evidence_missing:" in caveat for caveat in caveats):
        return _report(record, DecisionStatus.inconclusive, "collect validator evidence for every compared cell before deciding", caveats, **base_kwargs)

    directions = {item.direction for item in comparisons}
    if directions == {"unchanged"}:
        verdict = DecisionStatus.inconclusive
        recommended = "review the evidence; no task-level difference reached the decision threshold"
    elif "improved" in directions and "regressed" in directions:
        verdict = DecisionStatus.mixed
        recommended = "review the task-level trade-off before acting"
    elif "improved" in directions:
        verdict = DecisionStatus.improved
        recommended = "candidate meets the configured improvement threshold; review evidence before rollout"
    else:
        verdict = DecisionStatus.regressed
        recommended = "candidate regresses on at least one task; review evidence before rollout"
    comparison = ComparisonResult(
        baseline_configuration_id=baseline_id,
        candidate_configuration_id=candidate_id,
        decision_threshold=contract.decision_threshold,
        tasks=comparisons,
    )
    refs = _unique(ref for item in comparisons for ref in item.evaluation_refs)
    evidence = _unique(ref for item in comparisons for ref in item.evidence_refs)
    return _report(record, verdict, recommended, caveats, comparison=comparison, evaluation_refs=refs, evidence_refs=evidence, aggregation=aggregation, confidence="low")


def _report(record: RunRecord, verdict: DecisionStatus, recommended: str, caveats: list[str], **kwargs: object) -> DecisionReport:
    timestamp = compact_timestamp()
    return DecisionReport(
        decision_report_id=f"{record.id}::decision::{timestamp}",
        verdict=verdict,
        recommended_action=recommended,
        caveats=_dedupe(caveats) or ["decision_protected"],
        timestamp=timestamp,
        created_at=timestamp,
        **kwargs,
    )


def _denominator(results: list[CellResult], policy: str) -> list[CellResult]:
    if policy == "include_failed":
        return results
    return [r for r in results if r.status in {CellStatus.passed, CellStatus.failed}]


def _pass_rate(results: list[CellResult]) -> float:
    return sum(1 for result in results if result.pass_fail == "pass" or (result.pass_fail is None and result.status == CellStatus.passed)) / len(results)


def _auditable(result: CellResult, evaluations: dict[str, object]) -> bool:
    if result.status in {CellStatus.error, CellStatus.timeout}:
        return bool(result.artifact_refs or result.trace_refs or result.evidence_refs)
    return bool(result.evidence_refs) and any(
        evaluation is not None and getattr(evaluation, "evaluator_type", None) == "validator"
        for ref in result.evaluation_refs
        for evaluation in [evaluations.get(ref)]
    )


def _direction(delta: float, threshold: float | None) -> str | None:
    if threshold is None:
        return None
    if delta >= threshold:
        return "improved"
    if delta <= -threshold:
        return "regressed"
    return "unchanged"


def _unique(values) -> list[str]:  # type: ignore[no-untyped-def]
    return list(dict.fromkeys(str(value) for value in values))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
