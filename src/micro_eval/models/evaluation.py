"""Evaluation result models."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"


class EvaluationResult(BaseModel):
    """Validator or human evaluation for one cell."""

    schema_version: str = SCHEMA_VERSION
    evaluation_id: str
    cell_id: str
    evaluator_type: str = "validator"
    evaluator: str = "micro-eval"
    pass_fail: str | None = None
    score: float | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    evaluator_meta: dict[str, str | int | float | bool | None] | None = None
    rubric_hash: str | None = None
    comment: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = ""

    @field_validator("pass_fail")
    @classmethod
    def pass_fail_known(cls, value: str | None) -> str | None:
        if value is not None and value not in {"pass", "fail"}:
            raise ValueError("pass_fail must be pass, fail, or null")
        return value

    @model_validator(mode="after")
    def pass_fail_requires_evidence(self) -> "EvaluationResult":
        if self.pass_fail is not None and not self.evidence_refs:
            raise ValueError("pass_fail evaluation requires evidence_refs")
        return self
