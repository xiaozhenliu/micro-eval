"""Decision report and aggregation models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0"


class DecisionStatus(str, Enum):
    """Honest MVP decision taxonomy."""

    improved = "improved"
    regressed = "regressed"
    mixed = "mixed"
    inconclusive = "inconclusive"
    not_comparable = "not_comparable"
    needs_human_review = "needs_human_review"


class CostMetric(BaseModel):
    """Normalized cost metric for decision aggregation."""

    schema_version: str = SCHEMA_VERSION
    amount: float | None = None
    currency: str = "USD"
    source: str = "unavailable"


class ConfigurationStats(BaseModel):
    """Aggregated honest stats per configuration."""

    schema_version: str = SCHEMA_VERSION
    n_cells: int = 0
    n_successful: int = 0
    pass_rate: float | None = None
    pass_at_k: dict[int, float] | None = None
    pass_hat_k: dict[int, float] | None = None
    mean_latency_ms: float | None = None
    median_latency_ms: float | None = None
    total_cost: CostMetric | None = None
    denominator_policy: Literal["include_failed", "exclude_failed"] = "include_failed"
    caveats: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_stats(cls, value: Any) -> Any:
        """Accept MVP AggregationStats JSON embedded in older run.json files."""
        if not isinstance(value, dict) or "total" not in value:
            return value
        cost_usd = value.get("cost_usd")
        caveats: list[str] = []
        total = int(value.get("total") or 0)
        if total < 3:
            caveats.append("low_sample")
        return {
            "schema_version": value.get("schema_version", SCHEMA_VERSION),
            "n_cells": total,
            "n_successful": total,
            "pass_rate": value.get("pass_rate"),
            "pass_at_k": {1: value.get("pass_rate", 0.0)} if total == 1 else None,
            "pass_hat_k": {1: value.get("pass_rate", 0.0)} if total == 1 else None,
            "mean_latency_ms": _seconds_to_ms(value.get("mean_latency_s")),
            "median_latency_ms": _seconds_to_ms(value.get("median_latency_s")),
            "total_cost": None
            if cost_usd is None
            else {"amount": cost_usd, "currency": "USD", "source": "legacy_cost_usd"},
            "denominator_policy": "include_failed",
            "caveats": caveats,
        }


# Backward-compatible import name used by older tests/extensions.
AggregationStats = ConfigurationStats


class AggregationResult(BaseModel):
    """Run-level aggregation grouped by configuration."""

    schema_version: str = SCHEMA_VERSION
    per_configuration: dict[str, ConfigurationStats] = Field(default_factory=dict)

    def __getitem__(self, key: str) -> ConfigurationStats:
        """Provide read compatibility with legacy aggregation mappings."""
        return self.per_configuration[key]

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_mapping(cls, value: Any) -> Any:
        """Accept legacy {config_id: stats} aggregation mappings."""
        if isinstance(value, dict) and "per_configuration" not in value:
            per_configuration = {key: item for key, item in value.items() if key != "schema_version"}
            return {"schema_version": value.get("schema_version", SCHEMA_VERSION), "per_configuration": per_configuration}
        return value


class DecisionReport(BaseModel):
    """Evidence-linked decision report."""

    schema_version: str = SCHEMA_VERSION
    decision_report_id: str = ""
    verdict: DecisionStatus = DecisionStatus.inconclusive
    confidence: Literal["high", "medium", "low"] = "low"
    evaluation_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    aggregation: AggregationResult = Field(default_factory=AggregationResult)
    timestamp: str = ""
    recommended_action: str = "review evidence"
    created_at: str = ""

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_decision(cls, value: Any) -> Any:
        """Accept MVP decision JSON while preferring Phase 2 timestamp fields."""
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        if not migrated.get("timestamp") and migrated.get("created_at"):
            migrated["timestamp"] = migrated["created_at"]
        if not migrated.get("created_at") and migrated.get("timestamp"):
            migrated["created_at"] = migrated["timestamp"]
        return migrated


def _seconds_to_ms(value: Any) -> float | None:
    if value is None:
        return None
    return float(value) * 1000.0
