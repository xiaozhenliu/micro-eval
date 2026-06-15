"""Tests for configuration loader."""

from pathlib import Path

import pytest

from micro_eval.config.loader import (
    ConfigError,
    load_config,
    load_task,
    load_tasks,
    _parse_canonical_agent,
    _parse_configuration,
    _parse_legacy_agent,
)
from micro_eval.models.configuration import InputMode

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _by_role(config) -> dict:
    return {cfg.role: cfg for cfg in config.configurations}


def test_load_config_success():
    config = load_config(FIXTURES / "eval.yaml")
    assert config.project_name == "test-project"
    by_role = _by_role(config)
    assert by_role["baseline"].agent.name == "echo-baseline"
    assert by_role["candidate"].agent.name == "echo-candidate"
    assert by_role["baseline"].agent.command == ["cat"]
    assert by_role["baseline"].agent.input_mode == InputMode.stdin
    assert config.guardrails.max_concurrency > 1


def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config(Path("/nonexistent/eval.yaml"))


def test_load_config_invalid_yaml(tmp_path):
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text(": : : invalid")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(bad_file)


def test_load_config_not_mapping(tmp_path):
    bad_file = tmp_path / "list.yaml"
    bad_file.write_text("- item1\n- item2\n")
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_config(bad_file)


def test_load_config_missing_baseline(tmp_path):
    bad_file = tmp_path / "no_baseline.yaml"
    bad_file.write_text("candidate:\n  command: echo\n")
    with pytest.raises(ConfigError):
        load_config(bad_file)


def test_load_tasks_success():
    tasks = load_tasks(FIXTURES / "tasks")
    assert len(tasks) == 1
    assert tasks[0].id == "task-001"
    assert tasks[0].input_payload == "Hello, world!"
    assert tasks[0].expected_output == "Hello, world!"


def test_load_tasks_missing_dir():
    with pytest.raises(ConfigError, match="not found"):
        load_tasks(Path("/nonexistent/tasks"))


def test_load_tasks_empty_dir(tmp_path):
    tasks = load_tasks(tmp_path)
    assert tasks == []


def test_load_canonical_matrix_config_success():
    config = load_config(FIXTURES / "configs" / "eval_matrix.yaml")
    assert config.project_name == "matrix-project"
    assert len(config.configurations) == 2
    assert config.configurations[0].agent.command == ["cat"]
    assert config.configurations[1].repetitions == 2
    assert config.config_hash


def test_load_canonical_config_rejects_string_command(tmp_path):
    bad_file = tmp_path / "eval.yaml"
    bad_file.write_text(
        "project_name: bad\n"
        "configurations:\n"
        "  - id: bad\n"
        "    name: bad\n"
        "    agent:\n"
        "      name: bad\n"
        "      command: 'cat'\n"
    )
    with pytest.raises(ConfigError, match="argv list"):
        load_config(bad_file)


def test_load_canonical_config_rejects_output_dir_escape(tmp_path):
    bad_file = tmp_path / "eval.yaml"
    bad_file.write_text(
        "project_name: bad\n"
        "output_dir: ../outside\n"
        "configurations:\n"
        "  - id: bad\n"
        "    name: bad\n"
        "    agent:\n"
        "      name: bad\n"
        "      command: ['cat']\n"
    )
    with pytest.raises(ConfigError, match="output_dir"):
        load_config(bad_file)


def test_load_legacy_config_bridge_has_warning():
    config = load_config(FIXTURES / "configs" / "eval_legacy.yaml")
    by_role = _by_role(config)
    assert by_role["baseline"].agent.command == ["cat"]
    assert by_role["candidate"].agent.command == ["cat"]
    assert config.migration_warnings


def test_trace_config_accepts_langfuse_without_credentials(tmp_path: Path) -> None:
    config_path = tmp_path / "eval.yaml"
    config_path.write_text(
        """
project_name: trace-config
trace:
  enabled: true
  provider: langfuse
configurations:
  - id: agent
    name: Agent
    agent:
      name: agent
      command: ["python", "-c", "print('ok')"]
"""
    )

    config = load_config(config_path)

    assert config.trace.enabled is True
    assert config.trace.provider == "langfuse"


def test_judge_config_accepts_required_secret_names(tmp_path: Path) -> None:
    config_path = tmp_path / "eval.yaml"
    config_path.write_text(
        """
project_name: judge-config
judge:
  enabled: true
  provider: deepeval
  model: gpt-4.1-mini
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_API_KEY]
configurations:
  - id: agent
    name: Agent
    agent:
      name: agent
      command: ["python", "-c", "print('ok')"]
"""
    )

    config = load_config(config_path)

    assert config.judge.enabled is True
    assert config.judge.provider == "deepeval"
    assert config.judge.required_secrets == ["MICRO_EVAL_SECRET_OPENAI_API_KEY"]


# ---------------------------------------------------------------------------
# Error-path tests — target uncovered lines in loader.py
# ---------------------------------------------------------------------------

# --- load_task error paths (lines 82-83) ---

def test_load_task_invalid_task_id(tmp_path: Path) -> None:
    """TaskSpec validator raises ValueError for an unsafe id; load_task wraps it in ConfigError."""
    bad = tmp_path / "my task.yaml"
    bad.write_text("id: 'bad id with spaces'\nname: bad\ninput_payload: hi\n")
    with pytest.raises(ConfigError, match="Task validation error"):
        load_task(bad)


# --- _parse_canonical_config error paths (lines 110, 115) ---

def test_canonical_config_configurations_not_a_list(tmp_path: Path) -> None:
    """configurations key present but not a list raises ConfigError (line 110)."""
    bad = tmp_path / "eval.yaml"
    bad.write_text("project_name: bad\nconfigurations: not_a_list\n")
    with pytest.raises(ConfigError, match="configurations"):
        load_config(bad)


def test_canonical_config_root_timeout_s_propagated_to_guardrails(tmp_path: Path) -> None:
    """timeout_s at root level (line 115) is copied into guardrails when absent there."""
    cfg = tmp_path / "eval.yaml"
    cfg.write_text(
        "project_name: timeout-test\n"
        "timeout_s: 42\n"
        "configurations:\n"
        "  - id: a\n"
        "    name: A\n"
        "    agent:\n"
        "      name: a\n"
        "      command: ['echo']\n"
    )
    config = load_config(cfg)
    assert config.guardrails.timeout_s == 42.0


# --- _parse_configuration error paths (lines 155, 158) ---

def test_parse_configuration_entry_not_a_dict() -> None:
    """A non-dict entry in configurations[] raises ConfigError (line 155)."""
    with pytest.raises(ConfigError, match="must be mappings"):
        _parse_configuration("just a string")


def test_parse_configuration_agent_not_a_dict() -> None:
    """agent key present but not a dict raises ConfigError (line 158)."""
    with pytest.raises(ConfigError, match="agent must be a mapping"):
        _parse_configuration({"agent": "not-a-dict"})


# --- _parse_canonical_agent error paths (line 177) ---

def test_canonical_agent_missing_command() -> None:
    """No command key at all raises ConfigError (line 177)."""
    with pytest.raises(ConfigError, match="command is required"):
        _parse_canonical_agent({"name": "agent"})


# --- _parse_legacy_agent error paths (lines 193, 196, 199-200) ---

def test_legacy_agent_missing_command_field() -> None:
    """Legacy agent dict without 'command' raises ConfigError (line 193)."""
    with pytest.raises(ConfigError, match="missing 'command'"):
        _parse_legacy_agent({"name": "x"}, "baseline", 300.0)


def test_legacy_agent_command_not_string() -> None:
    """Legacy agent 'command' as a list raises ConfigError (line 196)."""
    with pytest.raises(ConfigError, match="must be a string"):
        _parse_legacy_agent({"command": ["cat"]}, "baseline", 300.0)


def test_legacy_agent_invalid_shlex_command() -> None:
    """A command string with unmatched quotes raises ConfigError (lines 199-200)."""
    with pytest.raises(ConfigError, match="Invalid legacy command"):
        _parse_legacy_agent({"command": "echo 'unclosed"}, "baseline", 300.0)


def test_legacy_agent_empty_dict() -> None:
    """An empty dict for a legacy agent raises ConfigError (line 191)."""
    with pytest.raises(ConfigError, match="Missing 'baseline' agent"):
        _parse_legacy_agent({}, "baseline", 300.0)


# --- _parse_task feature paths (lines 223, 227, 232, 234) ---

def test_load_task_expected_output_creates_expectation(tmp_path: Path) -> None:
    """expected_output with no explicit expectations[] auto-creates one (line 223)."""
    task_file = tmp_path / "t.yaml"
    task_file.write_text(
        "id: t1\nname: T\ninput_payload: hello\nexpected_output: world\n"
    )
    task = load_task(task_file)
    assert len(task.expectations) == 1
    assert task.expectations[0].value == "world"


def test_load_task_rubric_as_dict(tmp_path: Path) -> None:
    """A dict rubric is parsed into a RubricSpec (line 227)."""
    from micro_eval.models.task import RubricSpec

    task_file = tmp_path / "t.yaml"
    task_file.write_text(
        "id: t2\nname: T\ninput_payload: hi\n"
        "rubric:\n  text: Check output\n  dimensions: [clarity]\n"
    )
    task = load_task(task_file)
    assert isinstance(task.rubric, RubricSpec)
    assert task.rubric.text == "Check output"


def test_load_task_workspace_repo_alias(tmp_path: Path) -> None:
    """'repo' key in workspace is aliased to 'path' (line 232)."""
    task_file = tmp_path / "t.yaml"
    task_file.write_text(
        "id: t3\nname: T\ninput_payload: hi\n"
        "workspace:\n  repo: /some/path\n"
    )
    task = load_task(task_file)
    assert task.workspace.path == "/some/path"


def test_load_task_workspace_setup_commands_alias(tmp_path: Path) -> None:
    """'setup_commands' key in workspace is aliased to 'setup' (line 234)."""
    task_file = tmp_path / "t.yaml"
    task_file.write_text(
        "id: t4\nname: T\ninput_payload: hi\n"
        "workspace:\n  setup_commands:\n    - ['echo', 'hi']\n"
    )
    task = load_task(task_file)
    assert task.workspace.setup == [["echo", "hi"]]
