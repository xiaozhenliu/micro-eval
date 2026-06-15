"""Canonical task and expectation models."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class WorkspaceType(str, Enum):
    """Workspace setup strategy for a task."""

    blank = "blank"
    git_repo = "git_repo"
    files = "files"


class IsolationLevel(str, Enum):
    """Workspace isolation level (spec §3.4.5)."""

    logical = "logical"
    os_policy = "os_policy"
    container = "container"
    vm = "vm"


class TrustLevel(str, Enum):
    """Agent trust boundary (spec §3.4.3)."""

    trusted = "trusted"
    semi_trusted = "semi_trusted"
    untrusted = "untrusted"
    adversarial = "adversarial"


class NetworkPolicy(str, Enum):
    """Network access policy for sandboxed execution."""

    full = "full"
    allowlist = "allowlist"
    none = "none"


class FixtureSource(BaseModel):
    """A single fixture source with optional digest for reproducibility."""

    path: str
    digest: str | None = None


class ToolchainSpec(BaseModel):
    """Declared toolchain for fingerprinting (comparability dimension)."""

    runtime: str | None = None
    lockfile: str | None = None


class WorkspaceSpec(BaseModel):
    """Task workspace requirements."""

    schema_version: str = SCHEMA_VERSION
    type: WorkspaceType = WorkspaceType.blank
    path: str | None = None
    ref: str | None = None
    files: list[str] = Field(default_factory=list)
    setup: list[list[str]] = Field(default_factory=list)
    isolation_level: IsolationLevel = IsolationLevel.logical
    trust_level: TrustLevel = TrustLevel.trusted
    network_policy: NetworkPolicy | None = None
    fixtures: list[FixtureSource] = Field(default_factory=list)
    toolchain: ToolchainSpec | None = None


class ExpectationSpec(BaseModel):
    """Deterministic validation expectation."""

    schema_version: str = SCHEMA_VERSION
    type: str
    value: str | int | None = None
    path: str | None = None
    target: str | None = None
    stream: str = "output"
    command: list[str] | None = None
    argv: list[str] | None = None
    cwd: str | None = None
    timeout_s: float = 30.0

    @model_validator(mode="after")
    def validate_expectation(self) -> "ExpectationSpec":
        if self.target and self.stream == "output":
            self.stream = self.target
        if self.path and self.value is None:
            self.value = self.path
        if self.argv and not self.command:
            self.command = self.argv
        if self.type == "command":
            if not self.command:
                raise ValueError("command expectation requires argv command")
            if any(not isinstance(part, str) or not part for part in self.command):
                raise ValueError("command expectation argv entries must be non-empty strings")
        return self


class RubricSpec(BaseModel):
    """Human-readable rubric plus optional dimensions."""

    schema_version: str = SCHEMA_VERSION
    text: str = ""
    dimensions: list[str | dict[str, Any]] = Field(default_factory=list)


class TaskSpec(BaseModel):
    """A repeatable evaluation task."""

    schema_version: str = SCHEMA_VERSION
    id: str
    name: str
    description: str = ""
    input_payload: str
    expected_output: str | None = None
    rubric: str | RubricSpec | None = None
    expectations: list[ExpectationSpec] = Field(default_factory=list)
    workspace: WorkspaceSpec = Field(default_factory=WorkspaceSpec)
    business_impact_tier: int = 3
    tags: list[str] = Field(default_factory=list)
    revision_id: str = ""

    @field_validator("id")
    @classmethod
    def id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task id is required")
        if not SAFE_ID_RE.fullmatch(value):
            raise ValueError("task id must be path-safe: A-Z a-z 0-9 _ . : - only")
        return value
