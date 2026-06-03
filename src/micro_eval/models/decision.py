"""Decision report models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class DecisionStatus(str, Enum):
    """Honest MVP decision taxonomy."""

    improved = "improved"
    regressed = "regressed"
    mixed = "mixed"
    inconclusive = "inconclusive"
    not_comparable = "not_comparable"
    needs_human_review = "needs_human_review"


class AggregationStats(BaseModel):
    """Basic honest stats per configuration."""

    schema_version: str = SCHEMA_VERSION
    total: int = 0
    passed: int = 0
    pass_rate: float = 0.0
    mean_latency_s: float | None = None
    median_latency_s: float | None = None
    cost_usd: float | None = None


class DecisionReport(BaseModel):
    """Evidence-linked MVP decision."""

    schema_version: str = SCHEMA_VERSION
    verdict: DecisionStatus = DecisionStatus.inconclusive
    confidence: str = "low"
    evaluation_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    aggregation: dict[str, AggregationStats] = Field(default_factory=dict)
    recommended_action: str = "review evidence"
    created_at: str = ""
