"""Canonical configuration models."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from micro_eval.models.ids import canonical_digest

SCHEMA_VERSION = "1.0"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class InputMode(str, Enum):
    """How task input is passed to an agent."""

    stdin = "stdin"
    file = "file"


class OutputMode(str, Enum):
    """How agent output is selected."""

    stdout = "stdout"
    file = "file"
    directory = "directory"


class AgentSpec(BaseModel):
    """Canonical agent invocation configuration."""

    schema_version: str = SCHEMA_VERSION
    name: str
    command: list[str]
    input_mode: InputMode = InputMode.stdin
    output_mode: OutputMode = OutputMode.stdout
    timeout_s: float = 300.0
    env: dict[str, str] = Field(default_factory=dict)
    required_secrets: list[str] = Field(default_factory=list)

    @field_validator("command")
    @classmethod
    def command_must_be_argv(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("agent.command must be a non-empty argv list")
        if any(not isinstance(part, str) or part == "" for part in value):
            raise ValueError("agent.command entries must be non-empty strings")
        return value

    @field_validator("timeout_s")
    @classmethod
    def timeout_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_s must be positive")
        return value

    @field_validator("required_secrets")
    @classmethod
    def secrets_must_use_prefix(cls, value: list[str]) -> list[str]:
        bad = [name for name in value if not name.startswith("MICRO_EVAL_SECRET_")]
        if bad:
            raise ValueError("required_secrets must use MICRO_EVAL_SECRET_* names")
        return value


class ConfigurationSpec(BaseModel):
    """One comparable configuration in the run matrix."""

    schema_version: str = SCHEMA_VERSION
    id: str
    name: str
    agent: AgentSpec
    repetitions: int = 1
    role: str | None = None
    skills_profile: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("configuration id is required")
        if not SAFE_ID_RE.fullmatch(value):
            raise ValueError("configuration id must be path-safe: A-Z a-z 0-9 _ . : - only")
        return value

    @field_validator("repetitions")
    @classmethod
    def repetitions_must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("repetitions must be >= 1")
        return value

    @property
    def digest(self) -> str:
        """Return the replay-affecting configuration digest."""
        return canonical_digest(
            {
                "id": self.id,
                "agent": self.agent,
                "skills_profile": self.skills_profile,
                "parameters": self.parameters,
                "repetitions": self.repetitions,
            }
        )


class Guardrails(BaseModel):
    """Execution guardrails for a run."""

    schema_version: str = SCHEMA_VERSION
    max_concurrency: int = 2
    timeout_s: float = 300.0
    output_cap_bytes: int = 10 * 1024 * 1024
    artifact_cap_bytes: int = 10 * 1024 * 1024
    stop_on_cell_error: bool = False

    @field_validator("max_concurrency")
    @classmethod
    def concurrency_must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_concurrency must be >= 1")
        return value


class EvaluationContract(BaseModel):
    """MVP evaluation contract copied into planning and report context."""

    schema_version: str = SCHEMA_VERSION
    comparison_subject: str | None = None
    task_set_version: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    budget: dict[str, Any] | None = None
    decision_threshold: float | None = None
    inconclusive_policy: Literal["warn", "block"] = "warn"
    min_repetitions: int = 1
    required_evaluators: list[str] = Field(default_factory=lambda: ["validator"])
    denominator_policy: Literal["include_failed", "exclude_failed"] = "include_failed"

    @field_validator("required_evaluators", mode="before")
    @classmethod
    def migrate_required_evaluators(cls, value: Any) -> list[str]:
        if value is None:
            return ["validator"]
        if isinstance(value, int):
            return ["validator"] if value <= 0 else ["validator", *[f"human-{index}" for index in range(1, value + 1)]]
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("denominator_policy", mode="before")
    @classmethod
    def migrate_denominator_policy(cls, value: Any) -> str:
        if value == "all_cells":
            return "include_failed"
        if value == "completed_cells":
            return "exclude_failed"
        return value or "include_failed"

    @field_validator("min_repetitions")
    @classmethod
    def min_repetitions_must_be_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("min_repetitions must be >= 1")
        return value


class ProjectConfigV2(BaseModel):
    """Canonical project configuration."""

    schema_version: str = SCHEMA_VERSION
    project_name: str = "unnamed"
    description: str = ""
    configurations: list[ConfigurationSpec]
    tasks: list[str] = Field(default_factory=list)
    tasks_dir: str = "tasks"
    output_dir: str = ".micro-eval/runs"
    guardrails: Guardrails = Field(default_factory=Guardrails)
    evaluation: EvaluationContract = Field(default_factory=EvaluationContract)
    migration_warnings: list[str] = Field(default_factory=list)
    config_hash: str = ""


    @property
    def baseline(self):
        """Legacy baseline AgentConfig view when available."""
        from micro_eval.config.loader import legacy_agent_config

        cfg = next((item for item in self.configurations if item.role == "baseline"), self.configurations[0])
        return legacy_agent_config(cfg)

    @property
    def candidate(self):
        """Legacy candidate AgentConfig view when available."""
        from micro_eval.config.loader import legacy_agent_config

        cfg = next((item for item in self.configurations if item.role == "candidate"), self.configurations[-1])
        return legacy_agent_config(cfg)

    @property
    def parallel(self) -> bool:
        """Legacy parallel flag view."""
        return self.guardrails.max_concurrency > 1

    @field_validator("output_dir")
    @classmethod
    def output_dir_must_stay_inside_project(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise ValueError("output_dir must be a relative path inside the project root")
        return value

    @model_validator(mode="after")
    def require_configurations(self) -> "ProjectConfigV2":
        if not self.configurations:
            raise ValueError("at least one configuration is required")
        ids = [cfg.id for cfg in self.configurations]
        if len(ids) != len(set(ids)):
            raise ValueError("configuration ids must be unique")
        return self
