"""Configuration and task loading for micro-eval projects."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import yaml

from micro_eval.models.configuration import (
    AgentSpec,
    ConfigurationSpec,
    EvaluationContract,
    Guardrails,
    InputMode,
    OutputMode,
    ProjectConfigV2,
)
from micro_eval.models.ids import canonical_digest, sha256_text
from micro_eval.models.schema import AgentConfig
from micro_eval.models.task import ExpectationSpec, RubricSpec, TaskSpec, WorkspaceSpec


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


ProjectConfig = ProjectConfigV2


def load_config(path: Path | str) -> ProjectConfigV2:
    """Load canonical or legacy project configuration from eval.yaml."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    raw = _load_yaml_mapping(path)
    try:
        if "configurations" in raw:
            config = _parse_canonical_config(raw)
        else:
            config = _parse_legacy_config(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Config validation error in {path}: {exc}") from exc

    config.config_hash = canonical_digest(
        {
            "project_name": config.project_name,
            "description": config.description,
            "configurations": config.configurations,
            "tasks": config.tasks,
            "tasks_dir": config.tasks_dir,
            "guardrails": config.guardrails,
            "evaluation": config.evaluation,
        }
    )
    return config


def load_tasks(tasks_dir: Path | str) -> list[TaskSpec]:
    """Load all task YAML files from a directory."""
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.exists():
        raise ConfigError(f"Tasks directory not found: {tasks_dir}")

    tasks: list[TaskSpec] = []
    for task_file in sorted(tasks_dir.glob("*.yaml")):
        tasks.append(load_task(task_file))
    return tasks


def load_task(path: Path | str) -> TaskSpec:
    """Load one canonical task file."""
    path = Path(path)
    raw = _load_yaml_mapping(path)
    try:
        task = _parse_task(raw, path)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Task validation error in {path}: {exc}") from exc
    return task


def load_task_paths(config_path: Path | str, config: ProjectConfigV2) -> list[TaskSpec]:
    """Load task files referenced by canonical tasks or legacy tasks_dir."""
    base = Path(config_path).parent
    if config.tasks:
        return [load_task(base / task_path) for task_path in config.tasks]
    return load_tasks(base / config.tasks_dir)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        with open(path) as file:
            raw = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config must be a YAML mapping, got {type(raw).__name__}")
    return raw


def _parse_canonical_config(raw: dict[str, Any]) -> ProjectConfigV2:
    configurations_raw = raw.get("configurations")
    if not isinstance(configurations_raw, list):
        raise ConfigError("canonical config requires configurations[]")

    configurations = [_parse_configuration(item) for item in configurations_raw]
    guardrails_raw = raw.get("guardrails", {}) or {}
    if "timeout_s" in raw and "timeout_s" not in guardrails_raw:
        guardrails_raw = {**guardrails_raw, "timeout_s": raw["timeout_s"]}

    return ProjectConfigV2(
        project_name=raw.get("project_name", "unnamed"),
        description=raw.get("description", ""),
        configurations=configurations,
        tasks=list(raw.get("tasks", []) or []),
        tasks_dir=raw.get("tasks_dir", "tasks"),
        output_dir=raw.get("output_dir", ".micro-eval/runs"),
        guardrails=Guardrails(**guardrails_raw),
        evaluation=EvaluationContract(**(raw.get("evaluation", {}) or {})),
    )


def _parse_legacy_config(raw: dict[str, Any]) -> ProjectConfigV2:
    warnings = [
        "legacy baseline/candidate config converted to canonical configurations[]"
    ]
    timeout = float(raw.get("timeout_s", 300.0))
    baseline = _parse_legacy_agent(raw.get("baseline", {}), "baseline", timeout)
    candidate = _parse_legacy_agent(raw.get("candidate", {}), "candidate", timeout)
    return ProjectConfigV2(
        project_name=raw.get("project_name", "unnamed"),
        description=raw.get("description", ""),
        configurations=[baseline, candidate],
        tasks_dir=raw.get("tasks_dir", "tasks"),
        output_dir=raw.get("output_dir", ".micro-eval/runs"),
        guardrails=Guardrails(
            max_concurrency=2 if raw.get("parallel", True) else 1,
            timeout_s=timeout,
        ),
        evaluation=EvaluationContract(),
        migration_warnings=warnings,
    )


def _parse_configuration(data: Any) -> ConfigurationSpec:
    if not isinstance(data, dict):
        raise ConfigError("configuration entries must be mappings")
    agent_raw = data.get("agent", data)
    if not isinstance(agent_raw, dict):
        raise ConfigError("configuration.agent must be a mapping")
    agent = _parse_canonical_agent(agent_raw)
    config_id = data.get("id") or data.get("name") or agent.name
    return ConfigurationSpec(
        id=str(config_id),
        name=data.get("name", agent.name),
        agent=agent,
        repetitions=int(data.get("repetitions", 1)),
        role=data.get("role"),
        skills_profile=data.get("skills_profile", {}) or {},
        parameters=data.get("parameters", {}) or {},
    )


def _parse_canonical_agent(data: dict[str, Any]) -> AgentSpec:
    command = data.get("command")
    if isinstance(command, str):
        raise ConfigError("canonical agent.command must be an argv list, not a string")
    if not isinstance(command, list):
        raise ConfigError("agent.command is required and must be an argv list")
    return AgentSpec(
        name=data.get("name", "agent"),
        command=[str(part) for part in command],
        input_mode=InputMode(data.get("input_mode", "stdin")),
        output_mode=OutputMode(data.get("output_mode", "stdout")),
        timeout_s=float(data.get("timeout_s", 300.0)),
        env={str(k): str(v) for k, v in (data.get("env", {}) or {}).items()},
        required_secrets=[str(v) for v in (data.get("required_secrets", data.get("secrets", [])) or [])],
    )


def _parse_legacy_agent(data: Any, label: str, project_timeout: float) -> ConfigurationSpec:
    if not isinstance(data, dict) or not data:
        raise ConfigError(f"Missing '{label}' agent configuration")
    if "command" not in data:
        raise ConfigError(f"Agent '{label}' missing 'command' field")
    command = data["command"]
    if not isinstance(command, str):
        raise ConfigError(f"Legacy agent '{label}' command must be a string")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ConfigError(f"Invalid legacy command for '{label}': {exc}") from exc
    agent_name = data.get("name", label)
    agent = AgentSpec(
        name=agent_name,
        command=argv,
        input_mode=InputMode(data.get("input_mode", "stdin")),
        output_mode=OutputMode(data.get("output_mode", "stdout")),
        timeout_s=float(data.get("timeout_s", project_timeout)),
        env={str(k): str(v) for k, v in (data.get("env", {}) or {}).items()},
    )
    return ConfigurationSpec(
        id=label,
        name=agent_name,
        agent=agent,
        repetitions=1,
        role=label,
    )


def _parse_task(raw: dict[str, Any], path: Path) -> TaskSpec:
    expectations = [ExpectationSpec(**item) for item in raw.get("expectations", []) or []]
    expected = raw.get("expected_output")
    if expected is not None and not expectations:
        expectations.append(ExpectationSpec(type="contains", value=str(expected), stream="output"))
    rubric_raw = raw.get("rubric")
    rubric: str | RubricSpec | None
    if isinstance(rubric_raw, dict):
        rubric = RubricSpec(**rubric_raw)
    else:
        rubric = rubric_raw
    workspace_raw = dict(raw.get("workspace", {}) or {})
    if "repo" in workspace_raw and "path" not in workspace_raw:
        workspace_raw["path"] = workspace_raw["repo"]
    if "setup_commands" in workspace_raw and "setup" not in workspace_raw:
        workspace_raw["setup"] = workspace_raw["setup_commands"]
    task = TaskSpec(
        id=raw.get("id", raw.get("task_id", path.stem)),
        name=raw.get("name", path.stem),
        description=raw.get("description", ""),
        input_payload=raw.get("input_payload", raw.get("prompt", "")),
        expected_output=expected,
        rubric=rubric,
        expectations=expectations,
        workspace=WorkspaceSpec(**workspace_raw),
        business_impact_tier=int(raw.get("business_impact_tier", 3)),
        tags=list(raw.get("tags", []) or []),
    )
    task.revision_id = sha256_text(path.read_text())
    return task


def legacy_agent_config(configuration: ConfigurationSpec) -> AgentConfig:
    """Convert canonical configuration to the v0.1 legacy AgentConfig."""
    return AgentConfig(
        name=configuration.agent.name,
        command=" ".join(shlex.quote(part) for part in configuration.agent.command),
        input_mode=configuration.agent.input_mode,
        output_mode=configuration.agent.output_mode,
        timeout_s=configuration.agent.timeout_s,
        env=configuration.agent.env,
    )
