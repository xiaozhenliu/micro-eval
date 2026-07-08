"""Canonical run planning and result models."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from micro_eval.models.artifact import ArtifactRef, EvidenceItem, TraceRef
from micro_eval.models.configuration import ConfigurationSpec, Guardrails, JudgeConfig, TraceConfig
from micro_eval.models.decision import DecisionReport
from micro_eval.models.environment import CellSnapshot, ReplayCanonical, SameStartSnapshot, SnapshotGateResult
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.task import TaskSpec

SCHEMA_VERSION = "1.0"


class RunStatus(str, Enum):
    """Run lifecycle status."""

    planned = "planned"
    running = "running"
    completed = "completed"
    failed = "failed"
    partial = "partial"


class CellStatus(str, Enum):
    """Cell execution status."""

    passed = "pass"
    failed = "fail"
    error = "error"
    timeout = "timeout"


class RunCell(BaseModel):
    """One task/configuration/repetition execution cell."""

    schema_version: str = SCHEMA_VERSION
    cell_id: str
    task: TaskSpec
    configuration: ConfigurationSpec
    repetition: int = 1


class RunPlan(BaseModel):
    """Canonical execution plan consumed by the Execution Kernel."""

    schema_version: str = SCHEMA_VERSION
    run_id: str
    project_name: str
    created_at: str
    output_dir: str
    guardrails: Guardrails
    trace: TraceConfig = Field(default_factory=TraceConfig)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    cells: list[RunCell]
    config_hash: str
    migration_warnings: list[str] = Field(default_factory=list)
    same_start_snapshot: SameStartSnapshot | None = None
    replay_canonical: ReplayCanonical | None = None
    denominator_policy: Literal["include_failed", "exclude_failed"] = "include_failed"


class AdapterResult(BaseModel):
    """Facts returned by the Agent Adapter."""

    schema_version: str = SCHEMA_VERSION
    status: CellStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    output_artifacts: list[str] = Field(default_factory=list)
    latency_s: float = 0.0
    failure_mode: str | None = None
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    output_truncated: bool = False
    trace_id: str = ""


class CellResult(BaseModel):
    """Persisted canonical cell result."""

    schema_version: str = SCHEMA_VERSION
    cell_id: str
    run_id: str
    task_id: str
    configuration_id: str
    configuration_name: str
    repetition: int
    status: CellStatus
    score: float | None = None
    pass_fail: str | None = None
    output_summary: str = ""
    stdout_summary: str = ""
    stderr_summary: str = ""
    exit_code: int | None = None
    latency_s: float = 0.0
    failure_mode: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    output_truncated: bool = False
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    evaluation_refs: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
    cell_snapshot: CellSnapshot | None = None
    snapshot_gate_result: SnapshotGateResult | None = None
    # Conversational evaluation metadata (backward compatible)
    conversation_turns: int = 0
    conversation_ref: str | None = None


class RunRecord(BaseModel):
    """Canonical run record stored at .micro-eval/runs/{run_id}/run.json."""

    schema_version: str = SCHEMA_VERSION
    id: str
    project_name: str
    status: RunStatus = RunStatus.planned
    created_at: str
    completed_at: str | None = None
    output_dir: str
    config_hash: str = ""
    tasks: list[str] = Field(default_factory=list)
    configurations: list[str] = Field(default_factory=list)
    cells: list[str] = Field(default_factory=list)
    results: list[CellResult] = Field(default_factory=list)
    # Order cells were actually dispatched in, plus the seed when randomized, so a
    # run records its own execution order (order-effect provenance / replayable).
    execution_order: list[str] = Field(default_factory=list)
    execution_seed: int | None = None
    migration_warnings: list[str] = Field(default_factory=list)
    same_start_snapshot: SameStartSnapshot | None = None
    replay_canonical: ReplayCanonical | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    traces: list[TraceRef] = Field(default_factory=list)
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    decision: DecisionReport | None = None
    # Copied from project config at plan time; default keeps old run.json files compatible.
    denominator_policy: Literal["include_failed", "exclude_failed"] = "include_failed"
    # Server mode fields (optional, backward compatible)
    owner: str | None = None
    server_context: dict | None = None
