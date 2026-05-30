"""Configuration loading for micro-eval projects."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from micro_eval.models.schema import AgentConfig, InputMode, OutputMode, Task


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class ProjectConfig(BaseModel):
    """Top-level project configuration from eval.yaml."""
    project_name: str = "unnamed"
    baseline: AgentConfig
    candidate: AgentConfig
    tasks_dir: str = "tasks"
    output_dir: str = ".micro-eval/runs"
    parallel: bool = True
    timeout_s: float = 300.0


def load_config(path: Path | str) -> ProjectConfig:
    """Load and validate project configuration from eval.yaml."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}")

    if not isinstance(raw, dict):
        raise ConfigError(f"Config must be a YAML mapping, got {type(raw).__name__}")

    try:
        baseline = _parse_agent(raw.get("baseline", {}), "baseline")
        candidate = _parse_agent(raw.get("candidate", {}), "candidate")
    except (KeyError, ValueError) as e:
        raise ConfigError(f"Agent config error: {e}")

    timeout = raw.get("timeout_s", 300.0)
    return ProjectConfig(
        project_name=raw.get("project_name", "unnamed"),
        baseline=baseline,
        candidate=candidate,
        tasks_dir=raw.get("tasks_dir", "tasks"),
        output_dir=raw.get("output_dir", ".micro-eval/runs"),
        parallel=raw.get("parallel", True),
        timeout_s=timeout,
    )


def _parse_agent(data: dict, label: str) -> AgentConfig:
    """Parse an agent config section."""
    if not data:
        raise ConfigError(f"Missing '{label}' agent configuration")
    if "command" not in data:
        raise ConfigError(f"Agent '{label}' missing 'command' field")
    return AgentConfig(
        name=data.get("name", label),
        command=data["command"],
        input_mode=InputMode(data.get("input_mode", "stdin")),
        output_mode=OutputMode(data.get("output_mode", "stdout")),
        timeout_s=data.get("timeout_s", 300.0),
        env=data.get("env", {}),
    )


def load_tasks(tasks_dir: Path | str) -> list[Task]:
    """Load all task YAML files from a directory."""
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.exists():
        raise ConfigError(f"Tasks directory not found: {tasks_dir}")

    tasks: list[Task] = []
    for task_file in sorted(tasks_dir.glob("*.yaml")):
        try:
            with open(task_file) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {task_file}: {e}")

        if not isinstance(raw, dict):
            raise ConfigError(f"Task file {task_file} must be a mapping")

        task = Task(
            id=raw.get("id", task_file.stem),
            name=raw.get("name", task_file.stem),
            description=raw.get("description", ""),
            input_payload=raw.get("input_payload", ""),
            expected_output=raw.get("expected_output"),
            rubric=raw.get("rubric"),
            business_impact_tier=raw.get("business_impact_tier", 3),
            tags=raw.get("tags", []),
        )
        tasks.append(task)

    return tasks
