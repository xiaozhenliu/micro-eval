"""Artifact and evidence models."""

from __future__ import annotations

from pydantic import BaseModel, Field
from micro_eval.models.decision import CostMetric

SCHEMA_VERSION = "1.0"


class ArtifactRef(BaseModel):
    """Reference to a persisted artifact."""

    schema_version: str = SCHEMA_VERSION
    artifact_id: str
    kind: str
    path: str
    sha256: str
    size_bytes: int
    media_type: str = "text/plain"
    redacted: bool = True
    warning: str | None = None


class TraceRef(BaseModel):
    """Reference to a collected execution trace."""

    schema_version: str = SCHEMA_VERSION
    trace_id: str
    provider: str
    external_url: str | None = None
    cost: "CostMetric | None" = None
    summary: dict[str, str | int | float | bool | None] | None = None


class EvidenceItem(BaseModel):
    """Structured, citeable evidence item."""

    schema_version: str = SCHEMA_VERSION
    evidence_id: str
    kind: str
    summary: str
    source_kind: str | None = None
    source_ref: str | None = None
    cell_id: str | None = None
    status: str = "passed"
    severity: str = "info"
    artifact_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Manifest(BaseModel):
    """Run artifact manifest."""

    schema_version: str = SCHEMA_VERSION
    run_id: str
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    traces: list[TraceRef] = Field(default_factory=list)
