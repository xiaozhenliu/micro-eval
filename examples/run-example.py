#!/usr/bin/env python3
"""Run the source-checkout examples through a cross-platform Python entrypoint."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

EXAMPLE_NAME = "agent-codefix-showdown"


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    example_root = repo_root / "examples" / EXAMPLE_NAME
    config_name = "eval.yaml" if args.real else "eval.mock.yaml"
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

    mode = "real-agent" if args.real else "deterministic mock"
    print(f"Running {EXAMPLE_NAME} ({mode}) from {example_root}", flush=True)
    if args.real:
        print("Real-agent mode expects local agent CLIs to be installed and logged in.", flush=True)

    run_step("validate", [*command_prefix, "validate", "--config", config_name], cwd=example_root)
    if not args.skip_run:
        run_step(
            "run",
            [*command_prefix, "run", "--config", config_name, "--max-concurrency", str(args.max_concurrency)],
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
    if args.ui:
        ui_env = {"MICRO_EVAL_PROJECT_ROOT": str(example_root)}
        run_step("UI", [*command_prefix, "ui", "--port", str(args.port)], cwd=repo_root, env_overlay=ui_env)
    else:
        print(f"Optional UI: {Path(sys.executable).name} examples/run-example.py --ui", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the micro-eval source-checkout example.")
    parser.add_argument("--real", action="store_true", help="Run eval.yaml against real local agent CLIs.")
    parser.add_argument("--skip-run", action="store_true", help="Validate and regenerate reports from existing runs.")
    parser.add_argument("--max-concurrency", type=int, default=1, help="Maximum concurrent cells for the example run.")
    parser.add_argument("--ui", action="store_true", help="Launch the source-checkout UI after generating reports.")
    parser.add_argument("--port", type=int, default=3000, help="UI port when --ui is set.")
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
        src_dir = Path(__file__).resolve().parents[1] / "src"
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    if env_overlay:
        env.update(env_overlay)
    result = subprocess.run(list(command), cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
