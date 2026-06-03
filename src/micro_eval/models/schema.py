"""Pydantic models for micro-eval domain objects."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OutputMode(str, Enum):
    """How agent output is collected."""
    file = "file"
    directory = "directory"
    stdout = "stdout"


class InputMode(str, Enum):
    """How input is passed to the agent."""
    stdin = "stdin"
    file = "file"


class AgentConfig(BaseModel):
    """Configuration for a single agent under evaluation."""
    name: str
    command: str
    input_mode: InputMode = InputMode.stdin
    output_mode: OutputMode = OutputMode.stdout
    timeout_s: float = 300.0
    env: dict[str, str] = Field(default_factory=dict)


class Task(BaseModel):
    """A single evaluation task."""
    id: str
    name: str
    description: str = ""
    input_payload: str
    expected_output: Optional[str] = None
    rubric: Optional[str] = None
    business_impact_tier: int = 3
    tags: list[str] = Field(default_factory=list)


class TaskStatus(str, Enum):
    """Status of a task execution."""
    passed = "pass"
    failed = "fail"
    error = "error"
    timeout = "timeout"


class RunResult(BaseModel):
    """Result of running a single task with a single agent."""
    task_id: str
    agent_name: str
    status: TaskStatus
    score: Optional[float] = None
    output_summary: str = ""
    stdout_summary: str = ""
    stderr_summary: str = ""
    stdout_ref: Optional[str] = None
    stderr_ref: Optional[str] = None
    exit_code: Optional[int] = None
    output_dir: Optional[str] = None
    output_artifacts: list[str] = Field(default_factory=list)
    cost_usd: Optional[float] = None
    latency_s: float = 0.0
    failure_mode: Optional[str] = None


class EnvironmentSnapshot(BaseModel):
    """Captures the environment at the time of a run."""
    git_commit: Optional[str] = None
    config_hash: Optional[str] = None
    python_version: str = ""
    timestamp: str = ""


class Run(BaseModel):
    """A complete evaluation run."""
    id: str
    schema_version: str = "1.0"
    timestamp: str = ""
    baseline_agent: str
    candidate_agent: str
    tasks: list[str] = Field(default_factory=list)
    results: list[RunResult] = Field(default_factory=list)
    environment: EnvironmentSnapshot = Field(default_factory=EnvironmentSnapshot)
    execution_order: str = "parallel"
