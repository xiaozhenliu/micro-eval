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

DEFAULT_EXAMPLE = "agent-codefix-showdown"

# All known examples in recommended order
ALL_EXAMPLES = [
    "agent-codefix-showdown",
    "multi-task-matrix",
    "git-workspace-isolation",
    "conversational-eval",
    "team-server-quickstart",
]


def main() -> int:
    args = parse_args()

    if args.example == DEFAULT_EXAMPLE:
        return run_codefix_showdown(args)
    elif args.example == "all":
        return run_all_examples(args)
    else:
        return run_delegated_example(args.example, args)


def run_codefix_showdown(args: argparse.Namespace) -> int:
    """Run the default agent-codefix-showdown example with full flag support."""
    repo_root = Path(__file__).resolve().parents[1]
    example_root = repo_root / "examples" / DEFAULT_EXAMPLE
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
    print(f"Running {DEFAULT_EXAMPLE} ({mode}) from {example_root}", flush=True)
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


def run_delegated_example(name: str, args: argparse.Namespace) -> int:
    """Delegate to the example's own run.py script."""
    repo_root = Path(__file__).resolve().parents[1]
    run_script = repo_root / "examples" / name / "run.py"

    if not run_script.exists():
        print(f"Error: {run_script} not found.", file=sys.stderr, flush=True)
        return 2

    cmd = [sys.executable, str(run_script)]
    if args.skip_run:
        cmd.append("--skip-run")
    if args.max_concurrency != 1:
        cmd.extend(["--max-concurrency", str(args.max_concurrency)])
    if args.ui:
        cmd.append("--ui")
    if args.port != 3000:
        cmd.extend(["--port", str(args.port)])

    print(f"\n==> {name}", flush=True)
    result = subprocess.run(cmd, check=False)
    return result.returncode


def run_all_examples(args: argparse.Namespace) -> int:
    """Run all examples sequentially."""
    repo_root = Path(__file__).resolve().parents[1]

    for name in ALL_EXAMPLES:
        print(f"\n{'=' * 60}", flush=True)
        print(f"Example: {name}", flush=True)
        print(f"{'=' * 60}", flush=True)

        if name == DEFAULT_EXAMPLE:
            rc = run_codefix_showdown(args)
        else:
            rc = run_delegated_example(name, args)

        if rc != 0:
            print(f"\nExample '{name}' failed with exit code {rc}.", file=sys.stderr, flush=True)
            return rc

    print(f"\nAll {len(ALL_EXAMPLES)} examples completed successfully.", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the micro-eval source-checkout examples.")
    parser.add_argument(
        "--example",
        choices=[*ALL_EXAMPLES, "all"],
        default=DEFAULT_EXAMPLE,
        help=(
            "Which example to run. "
            "Default: agent-codefix-showdown (backward compatible). "
            "Use 'all' to run all examples sequentially."
        ),
    )
    parser.add_argument("--real", action="store_true", help="Run eval.yaml against real local agent CLIs (agent-codefix-showdown only).")
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
