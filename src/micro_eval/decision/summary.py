"""Basic honest decision summaries."""

from __future__ import annotations

from micro_eval.decision.aggregation import build_aggregation
from micro_eval.models.decision import DecisionReport, DecisionStatus
from micro_eval.models.ids import compact_timestamp
from micro_eval.models.run import RunRecord


def build_decision(record: RunRecord) -> DecisionReport:
    """Build a guarded decision from available cell facts."""
    aggregation = build_aggregation(record.results, traces=record.traces, denominator_policy=record.denominator_policy)
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
    if any("low_sample" in stats.caveats for stats in aggregation.per_configuration.values()):
        caveats.append("low_sample")
    for config_id, stats in aggregation.per_configuration.items():
        if "low_sample" in stats.caveats:
            caveats.append(f"low sample size for {config_id}: repetitions < 3")

    verdict = DecisionStatus.inconclusive
    recommended = "review the evidence for each cell and confirm the runs are comparable before acting"
    if snapshot_mismatches:
        verdict = DecisionStatus.not_comparable
        recommended = "fix same-start snapshot mismatches before comparing configurations"
    if not evaluation_refs or not evidence_refs:
        verdict = DecisionStatus.needs_human_review
        recommended = "collect evaluation evidence before deciding"

    timestamp = compact_timestamp()
    return DecisionReport(
        decision_report_id=f"{record.id}::decision::{timestamp}",
        verdict=verdict,
        confidence="low",
        evaluation_refs=evaluation_refs,
        evidence_refs=evidence_refs,
        caveats=_dedupe(caveats),
        aggregation=aggregation,
        recommended_action=recommended,
        timestamp=timestamp,
        created_at=timestamp,
    )


def _dedupe(values: list[str]) -> list[str]:
    """Keep caveat order while removing duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
