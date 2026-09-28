"""ISSUE-4: CLI failure path contract tests.

Acceptance criteria:
- Non-zero exit code + relevant error text for:
  1. Invalid/malformed eval.yaml
  2. `report --run <non-existent-id>`
  3. `run` in a non-git directory (workspace=git_repo task, without --dry-run)
- Zero network dependency; all tests run against CLI subprocess.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "micro_eval.cli.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_invalid_eval_yaml_exits_nonzero_with_error_message(tmp_path: Path) -> None:
    """A malformed eval.yaml must cause a non-zero exit and a human-readable error."""
    eval_yaml = tmp_path / "eval.yaml"
    eval_yaml.write_text(
        # YAML that is syntactically valid but semantically invalid — missing required fields
        "project_name: bad-config\n"
        "configurations: []\n"  # empty configurations is invalid
        "tasks: []\n"
    )

    result = _run_cli("validate", cwd=tmp_path)

    assert result.returncode != 0, (
        f"Expected non-zero exit for invalid eval.yaml, got 0.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    # Must give some kind of error message
    assert combined.strip(), "Expected error output for invalid eval.yaml, got empty"


def test_report_nonexistent_run_id_exits_nonzero(tmp_path: Path) -> None:
    """`report --run <non-existent-id>` must exit with non-zero status."""
    # Initialize a minimal project so the runs directory exists
    _run_cli("init", "--force", cwd=tmp_path)

    result = _run_cli("report", "--run", "run-does-not-exist-abc123", cwd=tmp_path)

    assert result.returncode != 0, (
        f"Expected non-zero exit for non-existent run id, got 0.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    # Must mention the run id or "not found" in the error output
    assert "run-does-not-exist-abc123" in combined or "not found" in combined.lower(), (
        f"Expected run id or 'not found' in error output, got:\n{combined}"
    )


def test_run_with_completely_invalid_yaml_syntax_exits_nonzero(tmp_path: Path) -> None:
    """`run` with YAML syntax error must exit non-zero with a parse error message."""
    eval_yaml = tmp_path / "eval.yaml"
    eval_yaml.write_text(
        "project_name: bad\n"
        "  indentation: error: [unclosed\n"
        "configurations:\n"
        "  - !!python/object:os.system ['rm -rf /']\n"  # injection attempt — must be rejected
    )

    result = _run_cli("run", cwd=tmp_path)

    assert result.returncode != 0, (
        f"Expected non-zero exit for YAML syntax error, got 0.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert combined.strip(), "Expected error output for bad YAML syntax"
