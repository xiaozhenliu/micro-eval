"""End-to-end test for the bundled starter-tasks template (GRO-554).

Registers the template, materializes a workspace from it (proving the
files-workspace copy that preserves the fixture directory name), injects
one configuration whose agent is a small deterministic test-local
"solver" script, then runs the real CLI `run` command against it and
asserts all 5 cells pass. This exercises the same path a real user (or
real agent) would go through: TemplateRegistry -> WorkspaceManager copy ->
eval.yaml with a configuration added -> `micro-eval run` -> command
expectation judged by `python -m micro_eval.tools.verify_protected`'s exit code.

Deterministic and fully offline: no network calls, no real LLM agent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from micro_eval.cli.main import app
from micro_eval.server.template import TemplateRegistry
from micro_eval.server.workspace import WorkspaceManager

TEMPLATE_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "micro_eval"
    / "server"
    / "seed_templates"
    / "starter-tasks"
)
SOLVER_SCRIPT = Path(__file__).resolve().parent / "support" / "starter_tasks_solver.py"

EXPECTED_TASK_IDS = {
    "date-range-overlap",
    "csv-quoted-fields",
    "lru-cache-order",
    "slugify-hyphens",
    "page-bounds",
}

runner = CliRunner()


def _inject_solver_configuration(eval_yaml_path: Path) -> None:
    """Add one configuration pointing at the test-local solver script.

    The shipped template ships `configurations: []` on purpose (agents are
    added in the browser); this mirrors that step for an offline test.
    """
    raw = yaml.safe_load(eval_yaml_path.read_text())
    raw["configurations"] = [
        {
            "id": "solver",
            "name": "test-local-solver",
            "role": "candidate",
            "repetitions": 1,
            "agent": {
                "name": "test-local-solver",
                "command": [sys.executable, str(SOLVER_SCRIPT)],
                "input_mode": "stdin",
                "output_mode": "stdout",
                "timeout_s": 30,
            },
        }
    ]
    eval_yaml_path.write_text(yaml.safe_dump(raw, sort_keys=False))


def _materialize_workspace(tmp_path: Path) -> Path:
    """Register the template, create a workspace from it, inject the solver."""
    data_root = tmp_path / "server-data"
    data_root.mkdir()

    registry = TemplateRegistry(data_root)
    registry.create(
        source_dir=TEMPLATE_SOURCE,
        template_id="starter-tasks",
        name="Starter tasks",
        description="Five small codefix problems",
    )

    ws_manager = WorkspaceManager(data_root)
    ws_meta = ws_manager.create(name="test-ws", owner="tester", template_id="starter-tasks")
    ws_dir = ws_manager.resolve_path(ws_meta.workspace_id)
    assert ws_dir is not None

    eval_yaml_path = ws_dir / "eval.yaml"
    assert eval_yaml_path.exists()
    # Confirm the fixture directory name survived the template copy verbatim
    # (WorkspaceManager.create copies each top-level template item preserving
    # its own name), before it goes through the engine's own files-workspace
    # copy inside the run.
    assert (ws_dir / "fixtures" / "date-range-overlap" / "date_range_overlap.py").exists()

    _inject_solver_configuration(eval_yaml_path)
    return eval_yaml_path


def _assert_all_five_pass(payload: dict) -> None:
    results = payload["results"]
    assert len(results) == 5
    assert {item["task_id"] for item in results} == EXPECTED_TASK_IDS
    failures = [item for item in results if item["status"] != "pass"]
    assert not failures, f"unexpected failing cells: {failures}"


def test_starter_tasks_pipeline_passes_with_in_process_cli(tmp_path: Path) -> None:
    """Engine pipeline check: files-workspace copy, validator cwd, exit-code
    judging. The solver copies known-good answers; it does not test any
    agent's ability to solve the problems."""
    eval_yaml_path = _materialize_workspace(tmp_path)

    result = runner.invoke(
        app,
        ["run", "--config", str(eval_yaml_path), "--max-concurrency", "1", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    _assert_all_five_pass(json.loads(result.output))


def test_starter_tasks_pipeline_passes_via_real_cli_subprocess(tmp_path: Path) -> None:
    """Same pipeline through the real interpreter entrypoint (argv-only
    subprocess), so packaging/entrypoint breakage cannot hide behind the
    in-process CliRunner."""
    eval_yaml_path = _materialize_workspace(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "micro_eval.cli.main",
            "run",
            "--config",
            str(eval_yaml_path),
            "--max-concurrency",
            "1",
            "--format",
            "json",
        ],
        cwd=eval_yaml_path.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    _assert_all_five_pass(json.loads(completed.stdout))
