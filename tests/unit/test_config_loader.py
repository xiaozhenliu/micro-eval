"""Tests for configuration loader."""

from pathlib import Path

import pytest

from micro_eval.config.loader import (
    ConfigError,
    load_config,
    load_tasks,
)
from micro_eval.models.schema import InputMode, OutputMode

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_load_config_success():
    config = load_config(FIXTURES / "eval.yaml")
    assert config.project_name == "test-project"
    assert config.baseline.name == "echo-baseline"
    assert config.candidate.name == "echo-candidate"
    assert config.baseline.command == "cat"
    assert config.baseline.input_mode == InputMode.stdin
    assert config.parallel is True


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
    assert config.baseline.command == "cat"
    assert config.candidate.command == "cat"
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
