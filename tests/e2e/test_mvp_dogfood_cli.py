"""Deterministic dogfood coverage for the MVP Golden Path."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_mvp_golden_path_cli_in_clean_project(tmp_path: Path) -> None:
    commands = [
        ["micro-eval", "init", "--force"],
        ["micro-eval", "validate", "--format", "json"],
        ["micro-eval", "run", "--dry-run", "--format", "json"],
        ["micro-eval", "run", "--max-concurrency", "2", "--format", "json"],
        ["micro-eval", "list", "--format", "json"],
        ["micro-eval", "report", "--format", "json"],
    ]
    outputs: list[subprocess.CompletedProcess[str]] = []
    for command in commands:
        outputs.append(
            subprocess.run(
                [sys.executable, "-m", "micro_eval.cli.main", *command[1:]],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=True,
            )
        )

    validate_payload = json.loads(outputs[1].stdout)
    dry_run_payload = json.loads(outputs[2].stdout)
    run_payload = json.loads(outputs[3].stdout)
    list_payload = json.loads(outputs[4].stdout)
    report_payload = json.loads(outputs[5].stdout)

    assert validate_payload["plan"]["cell_count"] == 2
    assert len(dry_run_payload["cells"]) == 2
    assert run_payload["same_start_snapshot"]
    assert run_payload["replay_canonical"]
    assert all(result["cell_snapshot"] for result in run_payload["results"])
    assert list_payload[0]["id"] == run_payload["id"]
    assert report_payload["id"] == run_payload["id"]
    assert (tmp_path / "tasks" / "templates" / "file-output.yaml").exists()
    assert (tmp_path / "tasks" / "templates" / "command-validation.yaml").exists()
