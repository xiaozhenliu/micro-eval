"""Configuration and task loading for micro-eval projects."""

from __future__ import annotations

import os
import re
import shlex
import stat
from pathlib import Path
from typing import IO, Any

import yaml

from micro_eval.engine.git_refs import INVALID_GIT_REF_HINT
from micro_eval.models.configuration import (
    AgentSpec,
    ConfigurationSpec,
    EvaluationContract,
    Guardrails,
    JudgeConfig,
    InputMode,
    OutputMode,
    ProjectConfigV2,
    TraceConfig,
)
from micro_eval.models.ids import canonical_digest, sha256_text
from micro_eval.models.task import ExpectationSpec, RubricSpec, TaskSpec, WorkspaceSpec


class ConfigError(Exception):
    """Raised when configuration is invalid or missing.

    ``reason`` carries a stable machine-readable cause when the error maps
    to a user-actionable fix (e.g. ``invalid_git_ref`` for a workspace ref
    that does not resolve to a commit); it is ``None`` for generic errors.
    """

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason
        super().__init__(message)


def config_error_hint(error: ConfigError) -> str:
    """Fixed actionable hint for a known structured ``ConfigError`` reason.

    Empty string for generic errors; callers append it to the message on
    CLI output paths only.
    """
    return INVALID_GIT_REF_HINT if error.reason == "invalid_git_ref" else ""


# Pydantic echoes the offending value (``input_value=...``) in validation
# errors; strip it here so no local CLI error surface repeats raw task or
# configuration input (the Team Server strips it again in _safe_detail).
_INPUT_VALUE_RE = re.compile(r"input_value=[^\n]*")


def _sanitize_validation_message(exc: BaseException) -> str:
    return _INPUT_VALUE_RE.sub("input_value=<omitted>", str(exc))


ProjectConfig = ProjectConfigV2


def load_config(path: Path | str, *, strict_paths: bool = False) -> ProjectConfigV2:
    """Load canonical or legacy project configuration from eval.yaml.

    With ``strict_paths`` (Team Server) the file is opened with ``O_NOFOLLOW``
    and must be a single-link regular file, so a symlink or hard link swapped
    in after any earlier check still cannot pull content from outside the
    workspace (round-7 review, 2026-09-13).
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    raw = _load_yaml_mapping(path, nofollow=strict_paths)
    try:
        if "configurations" in raw:
            config = _parse_canonical_config(raw)
        else:
            config = _parse_legacy_config(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Config validation error in {path}: {_sanitize_validation_message(exc)}"
        ) from exc

    config.config_hash = canonical_digest(
        {
            "project_name": config.project_name,
            "description": config.description,
            "configurations": config.configurations,
            "tasks": config.tasks,
            "tasks_dir": config.tasks_dir,
            "guardrails": config.guardrails,
            "evaluation": config.evaluation,
            "trace": config.trace,
            "judge": config.judge,
        }
    )
    return config


def _reject_link(path: Path, what: str) -> None:
    """Task inputs must be plain files inside the project: a symlink or a
    multi-link file could pull content from outside the project boundary."""
    if path.is_symlink():
        raise ConfigError(f"{what} must not be a symlink: {path.name}")
    try:
        if path.is_file() and path.stat().st_nlink > 1:
            raise ConfigError(f"{what} must not have multiple hard links: {path.name}")
    except OSError as exc:
        raise ConfigError(f"{what} cannot be inspected: {path.name}") from exc


def load_tasks(tasks_dir: Path | str) -> list[TaskSpec]:
    """Load all task YAML files from a directory."""
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.exists():
        raise ConfigError(f"Tasks directory not found: {tasks_dir}")
    _reject_link(tasks_dir, "Tasks directory")

    tasks: list[TaskSpec] = []
    for task_file in sorted(tasks_dir.glob("*.yaml")):
        tasks.append(load_task(task_file))
    return tasks


def load_task(path: Path | str) -> TaskSpec:
    """Load one canonical task file."""
    path = Path(path)
    _reject_link(path, "Task file")
    with _open_plain_file(path) as handle:
        text = handle.read()
    return _parse_task_text(text, path)


def _parse_task_text(text: str, path: Path) -> TaskSpec:
    """Parse task YAML already read into memory; the revision hashes the
    same text, so no second (path-based) read ever happens."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Task file must be a YAML mapping: {path.name}")
    try:
        return _parse_task(raw, path, source_text=text)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Task validation error in {path.name}: {_sanitize_validation_message(exc)}"
        ) from exc


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)


def _strict_parts(raw: str, what: str) -> list[str]:
    parts = raw.split("/")
    if raw.startswith("/") or any(part in ("", ".", "..") for part in parts):
        # The offending value is not echoed: it may be an absolute path.
        raise ConfigError(f"{what} must be a relative path inside the project (no leading '/', '.', '..')")
    if parts[0] == ".micro-eval":
        raise ConfigError(f"{what} must not point into the .micro-eval runtime directory")
    return parts


def _open_dir_below(base: Path, parts: list[str], what: str) -> int:
    """Open ``base/parts...`` one component at a time with ``O_NOFOLLOW``.

    Returns a directory fd the caller closes. Used by the strict (Team
    Server) loader so an intermediate directory swapped for a symlink after
    any earlier check is still refused (round-8 review, 2026-09-13).
    """
    try:
        fd = os.open(str(base), _DIR_FLAGS)
    except OSError as exc:
        raise ConfigError("project directory cannot be opened") from exc
    try:
        for part in parts:
            try:
                next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                raise ConfigError(f"{what} not found: {part}") from None
            except OSError as exc:
                raise ConfigError(f"{what} must not pass through a symlink: {part}") from exc
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_file_at(dfd: int, name: str, what: str) -> str:
    try:
        fd = os.open(name, _FILE_FLAGS, dir_fd=dfd)
    except FileNotFoundError:
        raise ConfigError(f"{what} not found: {name}") from None
    except OSError as exc:
        raise ConfigError(f"{what} must be a plain file (no symlink or hard link): {name}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ConfigError(f"{what} must be a plain file (no symlink or hard link): {name}")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            return handle.read()
    finally:
        if fd != -1:
            os.close(fd)


def _load_task_paths_strict(base: Path, config: ProjectConfigV2) -> list[TaskSpec]:
    if config.tasks:
        tasks: list[TaskSpec] = []
        for task_path in config.tasks:
            if not isinstance(task_path, str) or not task_path:
                raise ConfigError("task path must be a non-empty relative path")
            parts = _strict_parts(task_path, "task path")
            dfd = _open_dir_below(base, parts[:-1], "task path")
            try:
                text = _read_file_at(dfd, parts[-1], "Task file")
            finally:
                os.close(dfd)
            tasks.append(_parse_task_text(text, Path(task_path)))
        return tasks
    if not isinstance(config.tasks_dir, str) or not config.tasks_dir:
        raise ConfigError("tasks_dir must be a non-empty relative path")
    parts = _strict_parts(config.tasks_dir, "tasks_dir")
    dfd = _open_dir_below(base, parts, "tasks_dir")
    try:
        names = sorted(name for name in os.listdir(dfd) if name.endswith(".yaml"))
        return [_parse_task_text(_read_file_at(dfd, name, "Task file"), Path(name)) for name in names]
    finally:
        os.close(dfd)


def _project_relative(base: Path, raw: str, what: str, *, strict: bool) -> Path:
    """Resolve a project-relative reference without following symlinks.

    Always refuses a symlink on any component below ``base``. With
    ``strict`` (used by the Team Server, where the workspace directory is
    the trust boundary) it also refuses absolute paths and ``..`` segments;
    local projects may keep layouts such as ``../tasks/x.yaml`` relative to
    a config file that lives in a subdirectory (round-5 review, 2026-09-12).
    """
    if not isinstance(raw, str) or not raw:
        raise ConfigError(f"{what} must be a non-empty relative path")
    candidate = Path(raw)
    if strict and (candidate.is_absolute() or any(part in ("..", "") for part in raw.split("/"))):
        raise ConfigError(f"{what} must be a relative path inside the project: {raw}")
    current = base
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise ConfigError(f"{what} must not pass through a symlink: {raw}")
    return current


def load_task_paths(
    config_path: Path | str, config: ProjectConfigV2, *, strict_paths: bool = False
) -> list[TaskSpec]:
    """Load task files referenced by canonical tasks or legacy tasks_dir.

    ``strict_paths`` confines every reference to the config's directory (no
    absolute paths, no ``..``); the Team Server passes it because the
    workspace directory is the trust boundary there.
    """
    base = Path(config_path).parent
    if strict_paths:
        return _load_task_paths_strict(base, config)
    if config.tasks:
        return [
            load_task(_project_relative(base, task_path, "task path", strict=False))
            for task_path in config.tasks
        ]
    return load_tasks(_project_relative(base, config.tasks_dir, "tasks_dir", strict=False))


def _open_plain_file(path: Path) -> IO[str]:
    """Open ``path`` for reading without following a final symlink.

    The descriptor is checked to be a regular file with a single hard link
    before any content is read, closing the gap between a path-based check
    and the actual ``open``.
    """
    # O_NONBLOCK so a FIFO cannot block the open; fstat rejects it below.
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        raise ConfigError(f"File not found: {path.name}") from None
    except OSError as exc:
        # ELOOP: the final component is a symlink.
        raise ConfigError(f"{path.name} must be a plain file (no symlink or hard link)") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ConfigError(f"{path.name} must be a plain file (no symlink or hard link)")
        return os.fdopen(fd, "r", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise


def _load_yaml_mapping(path: Path, *, nofollow: bool = False) -> dict[str, Any]:
    try:
        handle = _open_plain_file(path) if nofollow else open(path)
        with handle as file:
            raw = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config must be a YAML mapping, got {type(raw).__name__}")
    return raw


def _tasks_list(raw: dict[str, Any]) -> list[str]:
    if "tasks" not in raw:
        return []
    field = raw["tasks"]
    if not isinstance(field, list):
        # An explicit ``tasks: null`` is a mistake, not "use tasks_dir".
        raise ConfigError("tasks must be a list of task paths")
    return list(field)


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
        tasks=_tasks_list(raw),
        tasks_dir=raw.get("tasks_dir", "tasks"),
        output_dir=raw.get("output_dir", ".micro-eval/runs"),
        guardrails=Guardrails(**guardrails_raw),
        evaluation=EvaluationContract(**(raw.get("evaluation", {}) or {})),
        trace=TraceConfig(**(raw.get("trace", {}) or {})),
        judge=JudgeConfig(**(raw.get("judge", {}) or {})),
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


def _parse_task(raw: dict[str, Any], path: Path, source_text: str | None = None) -> TaskSpec:
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
        # Conversational fields were silently dropped before 2026-09-12; the
        # judge only saw them via ad-hoc access. Map them like every other field.
        scenario=raw.get("scenario"),
        expected_outcome=raw.get("expected_outcome"),
        user_description=raw.get("user_description"),
    )
    # Callers that already hold the file text (e.g. the fd-based config editor)
    # pass it in so the revision is computed without a second, path-based read.
    task.revision_id = sha256_text(source_text if source_text is not None else path.read_text())
    return task
