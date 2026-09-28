"""CLI integration tests covering all sub-commands.

Tests use typer.testing.CliRunner so no subprocess is spawned and no
real agent is executed. Expensive I/O paths (ExecutionKernel.run,
RunStore.list_runs, RunStore.read_run, RunStore.latest_run_id) are patched
at the boundaries they are imported / instantiated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from micro_eval.cli.main import app
from micro_eval.models.run import CellResult, CellStatus, RunRecord, RunStatus

runner = CliRunner()

# ---------------------------------------------------------------------------
# Minimal YAML content for a valid canonical eval config + one task
# ---------------------------------------------------------------------------

_VALID_EVAL_YAML = """\
project_name: cli-integration-test
configurations:
  - id: baseline
    name: echo-baseline
    role: baseline
    repetitions: 1
    agent:
      name: echo-baseline
      command: ["cat"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 10
  - id: candidate
    name: echo-candidate
    role: candidate
    repetitions: 1
    agent:
      name: echo-candidate
      command: ["cat"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 10
tasks:
  - tasks/hello.yaml
output_dir: .micro-eval/runs
guardrails:
  max_concurrency: 2
  timeout_s: 30
"""

_VALID_TASK_YAML = """\
id: hello
name: Hello echo
description: Echo test
input_payload: "hello"
expected_output: "hello"
expectations:
  - type: contains
    stream: output
    value: "hello"
rubric: Output should echo input.
business_impact_tier: 3
tags: [smoke]
"""


# ---------------------------------------------------------------------------
# Fixtures: minimal on-disk project inside tmp_path
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path) -> Path:
    """Write eval.yaml + tasks/hello.yaml under tmp_path; return tmp_path."""
    (tmp_path / "tasks").mkdir()
    (tmp_path / "eval.yaml").write_text(_VALID_EVAL_YAML)
    (tmp_path / "tasks" / "hello.yaml").write_text(_VALID_TASK_YAML)
    return tmp_path


def _minimal_run_record(run_id: str = "run-test-001") -> RunRecord:
    """Return a minimal RunRecord with one completed cell."""
    result = CellResult(
        cell_id="hello||baseline||1",
        run_id=run_id,
        task_id="hello",
        configuration_id="baseline",
        configuration_name="echo-baseline",
        repetition=1,
        status=CellStatus.passed,
        score=1.0,
        latency_s=0.05,
    )
    return RunRecord(
        id=run_id,
        project_name="cli-integration-test",
        status=RunStatus.completed,
        created_at="2026-06-15T00:00:00Z",
        completed_at="2026-06-15T00:00:01Z",
        output_dir=".micro-eval/runs",
        tasks=["hello"],
        configurations=["baseline", "candidate"],
        cells=["hello||baseline||1"],
        results=[result],
    )


# ===========================================================================
# validate command
# ===========================================================================


class TestValidateCommand:
    def test_valid_config_exits_zero(self, tmp_path: Path) -> None:
        """validate with a well-formed eval.yaml exits 0 and shows Config OK."""
        _make_project(tmp_path)
        result = runner.invoke(app, ["validate", "--config", str(tmp_path / "eval.yaml")])
        assert result.exit_code == 0, result.output
        # Rich strips markup in test mode; check the plain text
        assert "Config OK" in result.output or "config_path" in result.output

    def test_valid_config_json_format(self, tmp_path: Path) -> None:
        """validate --format json produces parseable JSON with expected keys."""
        _make_project(tmp_path)
        result = runner.invoke(
            app, ["validate", "--config", str(tmp_path / "eval.yaml"), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["project_name"] == "cli-integration-test"
        assert "tasks" in payload
        assert "configurations" in payload
        assert "plan" in payload

    def test_missing_config_file_exits_nonzero(self, tmp_path: Path) -> None:
        """validate with a non-existent config exits 1 and reports an error."""
        result = runner.invoke(app, ["validate", "--config", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code == 1

    def test_malformed_yaml_exits_nonzero(self, tmp_path: Path) -> None:
        """validate with invalid YAML syntax exits 1."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(": : : not yaml")
        result = runner.invoke(app, ["validate", "--config", str(bad)])
        assert result.exit_code == 1

    def test_empty_config_exits_nonzero(self, tmp_path: Path) -> None:
        """validate with a YAML file that is just a list (not a mapping) exits 1."""
        bad = tmp_path / "list.yaml"
        bad.write_text("- item1\n- item2\n")
        result = runner.invoke(app, ["validate", "--config", str(bad)])
        assert result.exit_code == 1


# ===========================================================================
# run command
# ===========================================================================


class TestRunCommand:
    def test_dry_run_prints_plan_and_exits_zero(self, tmp_path: Path) -> None:
        """run --dry-run prints the plan without invoking the kernel."""
        _make_project(tmp_path)
        result = runner.invoke(
            app,
            ["run", "--config", str(tmp_path / "eval.yaml"), "--dry-run", "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "cells" in payload
        assert len(payload["cells"]) == 2  # baseline + candidate

    def test_run_with_missing_config_exits_nonzero(self, tmp_path: Path) -> None:
        """run with a missing config exits 1."""
        result = runner.invoke(app, ["run", "--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code == 1

    def test_run_with_malformed_yaml_exits_nonzero(self, tmp_path: Path) -> None:
        """run with invalid YAML exits 1."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(": invalid: yaml: content")
        result = runner.invoke(app, ["run", "--config", str(bad)])
        assert result.exit_code == 1

    def test_run_invokes_kernel_and_exits_zero(self, tmp_path: Path) -> None:
        """run with a valid config mocks the kernel and exits 0."""
        _make_project(tmp_path)
        record = _minimal_run_record()

        with patch("micro_eval.cli.run.ExecutionKernel") as MockKernel:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=record)
            MockKernel.return_value = mock_instance

            result = runner.invoke(
                app,
                ["run", "--config", str(tmp_path / "eval.yaml"), "--format", "json"],
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["id"] == "run-test-001"
        assert payload["status"] == "completed"

    def test_run_json_format_output(self, tmp_path: Path) -> None:
        """run --format json produces well-formed JSON with id and results."""
        _make_project(tmp_path)
        record = _minimal_run_record()

        with patch("micro_eval.cli.run.ExecutionKernel") as MockKernel:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=record)
            MockKernel.return_value = mock_instance

            result = runner.invoke(
                app,
                ["run", "--config", str(tmp_path / "eval.yaml"), "--format", "json"],
            )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "results" in payload
        assert payload["results"][0]["task_id"] == "hello"

    def test_run_text_format_produces_summary_table(self, tmp_path: Path) -> None:
        """run --format text prints a human-readable table."""
        _make_project(tmp_path)
        record = _minimal_run_record()

        with patch("micro_eval.cli.run.ExecutionKernel") as MockKernel:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=record)
            MockKernel.return_value = mock_instance

            result = runner.invoke(
                app,
                ["run", "--config", str(tmp_path / "eval.yaml")],
            )

        assert result.exit_code == 0, result.output
        # Text output should contain results summary header
        assert "Results" in result.output or "hello" in result.output


# ===========================================================================
# list command
# ===========================================================================


class TestListCommand:
    def test_list_with_runs_outputs_table(self, tmp_path: Path) -> None:
        """list with existing runs renders a table row per run."""
        record = _minimal_run_record()

        with patch("micro_eval.cli.list.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_runs.return_value = [record]
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0, result.output
        assert "run-test-001" in result.output

    def test_list_empty_directory_shows_friendly_message(self) -> None:
        """list with no runs prints a friendly no-runs message."""
        with patch("micro_eval.cli.list.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_runs.return_value = []
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0, result.output
        assert "No runs found" in result.output

    def test_list_json_format_returns_array(self) -> None:
        """list --format json produces a JSON array."""
        record = _minimal_run_record()

        with patch("micro_eval.cli.list.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_runs.return_value = [record]
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert payload[0]["id"] == "run-test-001"

    def test_list_json_format_empty_returns_empty_array(self) -> None:
        """list --format json with no runs produces an empty JSON array."""
        with patch("micro_eval.cli.list.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.list_runs.return_value = []
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload == []


# ===========================================================================
# init command
# ===========================================================================


class TestInitCommand:
    def test_init_creates_eval_yaml_and_task(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """init creates eval.yaml and tasks/hello.yaml in an empty directory."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "eval.yaml").exists()
        assert (tmp_path / "tasks" / "hello.yaml").exists()

    def test_init_creates_template_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """init creates both template files under tasks/templates/."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "tasks" / "templates" / "file-output.yaml").exists()
        assert (tmp_path / "tasks" / "templates" / "command-validation.yaml").exists()

    def test_init_outputs_confirmation_message(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """init prints a confirmation message listing created files."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0, result.output
        assert "eval.yaml" in result.output

    def test_init_fails_when_files_already_exist(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """init without --force exits 1 when eval.yaml already exists."""
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])  # first call creates files
        result = runner.invoke(app, ["init"])  # second call should fail
        assert result.exit_code == 1

    def test_init_force_overwrites_existing_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """init --force succeeds even when eval.yaml already exists."""
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["init", "--force"])
        assert result.exit_code == 0, result.output

    def test_init_eval_yaml_content_is_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """eval.yaml created by init is parseable by load_config."""
        from micro_eval.config.loader import load_config

        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        project = load_config(tmp_path / "eval.yaml")
        assert project.project_name == "demo-agent-eval"
        assert len(project.configurations) == 2


# ===========================================================================
# report command
# ===========================================================================


class TestReportCommand:
    def test_report_json_from_run_id_returns_run_data(self) -> None:
        """report --format json --run <id> returns the run record as JSON."""
        record = _minimal_run_record()

        with patch("micro_eval.cli.report.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.latest_run_id.return_value = "run-test-001"
            mock_instance.read_run.return_value = record
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["report", "--run", "run-test-001", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["id"] == "run-test-001"

    def test_report_text_format_shows_run_id(self) -> None:
        """report --format text shows the run id in the text output."""
        record = _minimal_run_record()

        with patch("micro_eval.cli.report.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.latest_run_id.return_value = "run-test-001"
            mock_instance.read_run.return_value = record
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["report", "--run", "run-test-001", "--format", "text"])

        assert result.exit_code == 0, result.output
        assert "run-test-001" in result.output

    def test_report_html_format_writes_file(self, tmp_path: Path) -> None:
        """report --format html writes an HTML file and prints confirmation."""
        record = _minimal_run_record()
        output_html = tmp_path / "report.html"

        with patch("micro_eval.cli.report.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.latest_run_id.return_value = "run-test-001"
            mock_instance.read_run.return_value = record
            MockStore.return_value = mock_instance

            result = runner.invoke(
                app,
                ["report", "--run", "run-test-001", "--format", "html", "--output", str(output_html)],
            )

        assert result.exit_code == 0, result.output
        assert output_html.exists()
        content = output_html.read_text()
        assert "run-test-001" in content
        assert "<!DOCTYPE html>" in content

    def test_report_invalid_run_id_exits_nonzero(self) -> None:
        """report with an unknown run id exits 1 with an error message."""
        with patch("micro_eval.cli.report.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.latest_run_id.return_value = None
            mock_instance.read_run.side_effect = Exception("Run not found: bad-id")
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["report", "--run", "bad-id", "--format", "json"])

        assert result.exit_code == 1

    def test_report_no_runs_exits_nonzero(self) -> None:
        """report with no runs and no explicit run id exits 1."""
        with patch("micro_eval.cli.report.RunStore") as MockStore:
            mock_instance = MagicMock()
            mock_instance.latest_run_id.return_value = None
            MockStore.return_value = mock_instance

            result = runner.invoke(app, ["report", "--format", "json"])

        assert result.exit_code == 1

    def test_report_from_run_file_json(self, tmp_path: Path) -> None:
        """report given a direct run.json path as positional arg returns JSON."""
        record = _minimal_run_record()
        # Write a run.json the command can load directly
        run_dir = tmp_path / ".micro-eval" / "runs" / "run-test-001"
        run_dir.mkdir(parents=True)
        run_json = run_dir / "run.json"
        run_json.write_text(record.model_dump_json(indent=2))

        result = runner.invoke(app, ["report", str(run_json), "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["id"] == "run-test-001"

    def test_report_missing_run_file_exits_nonzero(self, tmp_path: Path) -> None:
        """report given a nonexistent run.json path exits 1."""
        missing = tmp_path / "nonexistent-run.json"
        result = runner.invoke(app, ["report", str(missing), "--format", "json"])
        assert result.exit_code == 1
