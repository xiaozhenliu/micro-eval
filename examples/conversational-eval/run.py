#!/usr/bin/env python3
"""Run the conversational-eval example through a cross-platform Python entrypoint.

Prerequisites:
  - The `deepeval` package must be installed (see pyproject.toml extras).
  - An `OPENAI_API_KEY` environment variable must be set — the DeepEval
    ConversationSimulator and conversational metrics call an LLM provider
    to simulate the user side of the conversation and to score each turn.

Usage:
    python examples/conversational-eval/run.py          # validate + run + report
    python examples/conversational-eval/run.py --ui     # also launch the web UI
    python examples/conversational-eval/run.py --skip-run  # report from existing runs

Expected outcome:
  - 1 config x 2 tasks x 1 rep = 2 cells executed via the JSONL subprocess bridge
  - Each cell simulates a multi-turn conversation and scores all 5 conversational
    metrics: conversation_completeness, turn_relevancy, knowledge_retention,
    role_adherence, goal_accuracy
  - helpdesk-conversation task exercises a structured RubricSpec with named
    dimensions (context retention, empathy, solution quality)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

EXAMPLE_NAME = "conversational-eval"


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    example_root = Path(__file__).resolve().parent
    config_name = "eval.yaml"
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

    print(f"Running {EXAMPLE_NAME} from {example_root}", flush=True)
    print("This example demonstrates:", flush=True)
    print("  - Multi-turn conversational evaluation via DeepEval ConversationSimulator", flush=True)
    print("  - JSONL subprocess bridge (agent_bridge.py) for turn-by-turn agent I/O", flush=True)
    print("  - All 5 conversational metrics: conversation_completeness, turn_relevancy, ", flush=True)
    print("    knowledge_retention, role_adherence, goal_accuracy", flush=True)
    print("  - Structured RubricSpec with named dimensions (helpdesk-conversation task)", flush=True)
    print(
        "Note: scoring requires DeepEval installed and OPENAI_API_KEY set "
        "(or another configured LLM provider) to simulate and score turns.",
        flush=True,
    )

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
        "Observe: each cell's trace shows the simulated multi-turn conversation "
        "and per-turn scores for all 5 conversational metrics.",
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
        default=1,
        help="Maximum concurrent cells (default: 1).",
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
