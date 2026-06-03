"""Environment, snapshot, and replay models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class SnapshotGateResult(BaseModel):
    """Comparison result between intended and observed start state."""

    schema_version: str = SCHEMA_VERSION
    status: Literal["pass", "warn", "fail"] = "warn"
    mismatch_fields: list[str] = Field(default_factory=list)
    gate_version: str = "1.0"
    caveats: list[str] = Field(default_factory=list)
