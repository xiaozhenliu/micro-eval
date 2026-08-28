"""Environment, snapshot, and replay models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from micro_eval.models.task import WorkspaceType

SCHEMA_VERSION = "1.0"


class SameStartSnapshot(BaseModel):
    """Run-level intended comparable start state."""

    schema_version: str = SCHEMA_VERSION
    workspace_type: str = "blank"
    git_commit: str | None = None
    dirty: bool | None = None
    config_hash: str = ""
    configuration_digests: dict[str, str] = Field(default_factory=dict)
    task_revisions: dict[str, str] = Field(default_factory=dict)
    python_version: str = ""
    setup_commands_digest: str | None = None
    guardrails_digest: str = ""
    sandbox_resource_limits: dict[str, str | int | float | bool | None] | None = None
    workspace_map: dict[str, str | None] | None = None
    sandbox_policy: str | None = None
    network_policy: str | None = None
    toolchain_fingerprint: str | None = None
    fixture_digests: dict[str, str] = Field(default_factory=dict)
    timestamp: str = ""
    caveats: list[str] = Field(default_factory=list)


class ReplayCanonical(BaseModel):
    """Replay-affecting canonical inputs; excludes observation metadata."""

    schema_version: str = SCHEMA_VERSION
    tool_version: str = ""
    config_hash: str = ""
    task_ids: list[str] = Field(default_factory=list)
    task_revisions: dict[str, str] = Field(default_factory=dict)
    configuration_ids: list[str] = Field(default_factory=list)
    configuration_digests: dict[str, str] = Field(default_factory=dict)
    workspace_type: str = "blank"
    git_commit: str | None = None
    workspace_map: dict[str, str | None] | None = None
    workspace_fingerprint: str = ""
    setup_commands_digest: str | None = None
    guardrails_digest: str = ""
    max_concurrency: int = 1
    digest: str = ""


class CellSnapshot(BaseModel):
    """Observed cell execution start/end facts."""

    schema_version: str = SCHEMA_VERSION
    workspace_path: str = ""
    git_commit: str | None = None
    dirty: bool | None = None
    setup_exit_code: int | None = None
    timestamp: str = ""
    cleanup_status: str | None = None
    cleanup_error: str | None = None


@dataclass(frozen=True)
class WorkspaceObservation:
    """Bounded raw facts collected from a live workspace before validation.

    Environment owns collection and interpretation of provider output, but it
    deliberately does not know about ArtifactRef or run-directory layout.
    ArtifactStore turns this observation into durable, redacted references.
    """

    workspace_type: WorkspaceType
    diff_text: str | None = None
    diff_truncated: bool = False
    warnings: tuple[str, ...] = ()


class SnapshotGateResult(BaseModel):
    """Comparison result between intended and observed start state."""

    schema_version: str = SCHEMA_VERSION
    status: Literal["pass", "warn", "fail"] = "warn"
    mismatch_fields: list[str] = Field(default_factory=list)
    gate_version: str = "1.0"
    caveats: list[str] = Field(default_factory=list)
