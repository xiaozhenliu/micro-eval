"""Human evaluation helpers."""

from __future__ import annotations

import os

from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.ids import compact_timestamp, sha256_text


def build_human_evaluation(
    *,
    cell_id: str,
    pass_fail: str | None,
    score: float | None,
    scores: dict[str, float] | None = None,
    comment: str = "",
    evaluator: str = "human",
) -> tuple[EvaluationResult, EvidenceItem]:
    """Create an append-only human evaluation plus its evidence item."""
    timestamp = compact_timestamp()
    safe_comment = _redact_env_secrets(comment)
    digest = sha256_text(f"{cell_id}|{pass_fail}|{score}|{scores}|{safe_comment}|{evaluator}|{timestamp}")[:12]
    evaluation_id = f"{cell_id}::human::{digest}"
    evidence_id = f"{cell_id}::evidence::human-{digest}"
    evidence = EvidenceItem(
        evidence_id=evidence_id,
        kind="annotation",
        source_kind="evaluation_id",
        source_ref=evaluation_id,
        cell_id=cell_id,
        status="passed" if pass_fail == "pass" else "failed" if pass_fail == "fail" else "skipped",
        severity="info",
        summary=(safe_comment or f"human evaluation: {pass_fail or 'unscored'}")[:500],
        metadata={"evaluator": evaluator},
    )
    evaluation = EvaluationResult(
        evaluation_id=evaluation_id,
        cell_id=cell_id,
        evaluator_type="human",
        evaluator=evaluator,
        pass_fail=pass_fail,
        score=score,
        scores=scores or {},
        comment=safe_comment,
        evidence_refs=[evidence_id],
        created_at=timestamp,
    )
    return evaluation, evidence


def _redact_env_secrets(text: str) -> str:
    redacted = text
    for name, value in os.environ.items():
        if name.startswith("MICRO_EVAL_SECRET_") and value and len(value) >= 4:
            redacted = redacted.replace(value, f"[REDACTED:{name}]")
    return redacted
