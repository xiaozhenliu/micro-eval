"""Basic honest decision summaries."""

from __future__ import annotations

from statistics import mean, median

from micro_eval.models.decision import AggregationStats, DecisionReport, DecisionStatus
from micro_eval.models.ids import compact_timestamp
from micro_eval.models.run import CellResult, RunRecord


def build_decision(record: RunRecord) -> DecisionReport:
    """Build a guarded MVP decision from available cell facts."""
    aggregation: dict[str, AggregationStats] = {}
    by_config: dict[str, list[CellResult]] = {}
    for result in record.results:
        by_config.setdefault(result.configuration_id, []).append(result)

    for config_id, results in by_config.items():
        total = len(results)
        passed = sum(
            1
            for result in results
            if (result.pass_fail == "pass" if result.pass_fail is not None else result.status.value == "pass")
        )
        latencies = [result.latency_s for result in results]
        aggregation[config_id] = AggregationStats(
            total=total,
            passed=passed,
            pass_rate=passed / total if total else 0.0,
            mean_latency_s=mean(latencies) if latencies else None,
            median_latency_s=median(latencies) if latencies else None,
        )

    evaluation_refs = [ref for result in record.results for ref in result.evaluation_refs]
    evidence_refs = [ref for result in record.results for ref in result.evidence_refs]
    caveats = list(record.migration_warnings)
    if record.same_start_snapshot and record.same_start_snapshot.caveats:
        caveats.extend(record.same_start_snapshot.caveats)
    snapshot_mismatches = [
        result
        for result in record.results
        if result.snapshot_gate_result and result.snapshot_gate_result.status != "pass"
    ]
    for result in snapshot_mismatches:
        fields = ", ".join(result.snapshot_gate_result.mismatch_fields) or "cleanup/caveat"
        caveats.append(f"snapshot gate warning for {result.cell_id}: {fields}")
    if len(record.results) < len(record.cells):
        caveats.append("run is partial; not all cells completed")
    if len(record.configurations) < 2:
        caveats.append("single configuration run cannot produce comparative verdict")
    for config_id, stats in aggregation.items():
        if stats.total < 3:
            caveats.append(f"low sample size for {config_id}: repetitions < 3")

    verdict = DecisionStatus.inconclusive
    recommended = "review evidence and complete P0-b comparability gate"
    if snapshot_mismatches:
        verdict = DecisionStatus.not_comparable
        recommended = "fix same-start snapshot mismatches before comparing configurations"
    if not evaluation_refs or not evidence_refs:
        verdict = DecisionStatus.needs_human_review
        recommended = "collect evaluation evidence before deciding"

    return DecisionReport(
        verdict=verdict,
        confidence="low",
        evaluation_refs=evaluation_refs,
        evidence_refs=evidence_refs,
        caveats=caveats,
        aggregation=aggregation,
        recommended_action=recommended,
        created_at=compact_timestamp(),
    )
