#!/usr/bin/env python3
"""Run the multi-task-matrix example through a cross-platform Python entrypoint.

Usage:
    python examples/multi-task-matrix/run.py          # validate + run + report
    python examples/multi-task-matrix/run.py --ui     # also launch the web UI
    python examples/multi-task-matrix/run.py --skip-run  # report from existing runs

Expected outcome:
  - 2 configs × 3 tasks × 2 reps = 12 cells executed
  - decision.json verdict = inconclusive (alpha all-pass vs beta partial-fail)
  - All four expectation types exercised: exit_code, contains, file_exists, command
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

EXAMPLE_NAME = "multi-task-matrix"


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    example_root = Path(__file__).resolve().parent
    config_name = "eval.mock.yaml"
    command_prefix = micro_eval_command(repo_root)

    if command_prefix is None:
        print(
            "Could not find a runnable micro-eval CLI. Install uv, install micro-eval, "
            "or run this script from a Python environment with the project dependencies.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.max_concurrency < 1:
        print("--max-concurrency must be >= 1", file=sys.stderr, flush=True)
        return 2

    print(f"Running {EXAMPLE_NAME} (deterministic mock) from {example_root}", flush=True)
    print("This example demonstrates:", flush=True)
    print("  - 2 configs × 3 tasks × 2 reps = 12 cells (multi-task matrix)", flush=True)
    print("  - All 4 expectation types: exit_code, contains, file_exists, command", flush=True)
    print("  - Workspace setup commands", flush=True)
    print("  - Checker-beta partial failure (generate-report task)", flush=True)
    print("  - Inconclusive decision (baseline all-pass vs candidate partial-fail)", flush=True)

    run_step("validate", [*command_prefix, "validate", "--config", config_name], cwd=example_root)
    if not args.skip_run:
        run_step(
            "run",
            [
                *command_prefix,
                "run",
                "--config",
                config_name,
                "--max-concurrency",
                str(args.max_concurrency),
            ],
            cwd=example_root,
        )
    run_step("list", [*command_prefix, "list"], cwd=example_root)
    run_step("text report", [*command_prefix, "report", "--format", "text"], cwd=example_root)
    run_step(
        "HTML report",
        [*command_prefix, "report", "--format", "html", "--output", "report.html"],
        cwd=example_root,
    )

    print(f"\nDone. Static report: {example_root / 'report.html'}", flush=True)
    print(
        "Observe: checker-alpha (baseline) shows all PASS; "
        "checker-beta (candidate) shows FAIL on generate-report.",
        flush=True,
    )
    if args.ui:
        ui_env = {"MICRO_EVAL_PROJECT_ROOT": str(example_root)}
        run_step("UI", [*command_prefix, "ui", "--port", str(args.port)], cwd=repo_root, env_overlay=ui_env)
    else:
        print(
            f"Optional UI: python examples/{EXAMPLE_NAME}/run.py --ui",
            flush=True,
        )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run the {EXAMPLE_NAME} micro-eval example.")
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Validate and regenerate reports from existing runs without re-running.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2,
        help="Maximum concurrent cells (default: 2).",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch the web UI after generating reports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="UI port when --ui is set (default: 3000).",
    )
    return parser.parse_args()


def micro_eval_command(repo_root: Path) -> list[str] | None:
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--project", str(repo_root), "micro-eval"]
    installed_cli = shutil.which("micro-eval")
    if installed_cli:
        return [installed_cli]
    src_dir = repo_root / "src"
    if src_dir.exists():
        return [sys.executable, "-m", "micro_eval.cli.main"]
    return None


def run_step(
    label: str,
    command: Sequence[str],
    *,
    cwd: Path,
    env_overlay: dict[str, str] | None = None,
) -> None:
    print(f"\n==> {label}", flush=True)
    env = os.environ.copy()
    if command[:3] == [sys.executable, "-m", "micro_eval.cli.main"]:
        src_dir = Path(__file__).resolve().parents[2] / "src"
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    if env_overlay:
        env.update(env_overlay)
    result = subprocess.run(list(command), cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
