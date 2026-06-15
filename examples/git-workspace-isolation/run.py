#!/usr/bin/env python3
"""One-click runner for the git-workspace-isolation example.

Demonstrates:
  - git_repo workspace + git worktree isolation (each cell = isolated worktree copy)
  - OS policy sandbox config (Seatbelt on macOS / Bubblewrap on Linux / degrades gracefully)
  - Fixture digest + toolchain fingerprint in SameStartSnapshot
  - Trend analysis with drift breakpoint (two runs with different config digests)

Usage:
    python examples/git-workspace-isolation/run.py          # run both passes + reports
    python examples/git-workspace-isolation/run.py --ui     # open UI after runs
    python examples/git-workspace-isolation/run.py --skip-run  # reports only (reuse existing runs)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

EXAMPLE_NAME = "git-workspace-isolation"
FIXTURE_REPO_NAME = "fixture-repo"


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    example_root = Path(__file__).resolve().parent
    fixture_repo = example_root / FIXTURE_REPO_NAME

    # 1. Verify git is available.
    if not _check_git():
        print(
            "ERROR: git is not available on PATH.\n"
            "git is required for git_repo workspace isolation.\n"
            "Install git and re-run this script.",
            file=sys.stderr,
        )
        return 2

    command_prefix = _micro_eval_command(repo_root)
    if command_prefix is None:
        print(
            "ERROR: Could not find a runnable micro-eval CLI.\n"
            "Install uv, install micro-eval, or run from a Python environment "
            "with project dependencies.",
            file=sys.stderr,
        )
        return 2

    if args.max_concurrency < 1:
        print("ERROR: --max-concurrency must be >= 1", file=sys.stderr)
        return 2

    print(f"Running {EXAMPLE_NAME} example from {example_root}", flush=True)

    # 2. Ensure fixture-repo is a valid git repo.
    if not args.skip_run:
        _ensure_fixture_repo_is_git(fixture_repo)

    # 3. First run: eval.mock.yaml (baseline config digest).
    if not args.skip_run:
        print("\n--- Pass 1: eval.mock.yaml (timeout_s=60) ---", flush=True)
        _run_step(
            "validate (v1)",
            [*command_prefix, "validate", "--config", "eval.mock.yaml"],
            cwd=example_root,
        )
        _run_step(
            "run (v1)",
            [
                *command_prefix,
                "run",
                "--config",
                "eval.mock.yaml",
                "--max-concurrency",
                str(args.max_concurrency),
            ],
            cwd=example_root,
        )

    # 4. Second run: eval.mock.v2.yaml (timeout_s changed → different config digest → drift breakpoint).
    if not args.skip_run:
        print(
            "\n--- Pass 2: eval.mock.v2.yaml (timeout_s=120, triggers drift breakpoint) ---",
            flush=True,
        )
        _run_step(
            "validate (v2)",
            [*command_prefix, "validate", "--config", "eval.mock.v2.yaml"],
            cwd=example_root,
        )
        _run_step(
            "run (v2)",
            [
                *command_prefix,
                "run",
                "--config",
                "eval.mock.v2.yaml",
                "--max-concurrency",
                str(args.max_concurrency),
            ],
            cwd=example_root,
        )

    # 5. List runs and generate reports.
    _run_step("list", [*command_prefix, "list"], cwd=example_root)
    _run_step(
        "text report",
        [*command_prefix, "report", "--format", "text"],
        cwd=example_root,
    )
    _run_step(
        "HTML report",
        [*command_prefix, "report", "--format", "html", "--output", "report.html"],
        cwd=example_root,
    )

    # 6. Print post-run instructions.
    _print_instructions(example_root, args)

    # 7. Optionally launch UI.
    if args.ui:
        ui_env = {"MICRO_EVAL_PROJECT_ROOT": str(example_root)}
        _run_step(
            "UI",
            [*command_prefix, "ui", "--port", str(args.port)],
            cwd=repo_root,
            env_overlay=ui_env,
        )

    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the git-workspace-isolation example.")
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Skip execution; regenerate reports from existing runs.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Max concurrent cells (default 1 for deterministic ordering).",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch the local Web UI after generating reports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="UI port when --ui is set (default 3000).",
    )
    return parser.parse_args()


def _check_git() -> bool:
    """Return True if git is available on PATH."""
    return shutil.which("git") is not None


def _ensure_fixture_repo_is_git(fixture_repo: Path) -> None:
    """Initialize fixture-repo as a git repo if it is not already one."""
    git_dir = fixture_repo / ".git"
    if git_dir.exists():
        print(f"\nfixture-repo already initialized as git repo: {fixture_repo}", flush=True)
        return

    print(f"\nInitializing fixture-repo as a git repo: {fixture_repo}", flush=True)

    def _git(*args: str) -> None:
        result = subprocess.run(
            ["git", *args],
            cwd=fixture_repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"ERROR: git {' '.join(args)} failed:\n{result.stderr}", file=sys.stderr)
            raise SystemExit(result.returncode)

    _git("init", "-b", "main")
    _git("config", "user.email", "micro-eval-example@localhost")
    _git("config", "user.name", "micro-eval example")
    _git("add", "-A")
    _git("commit", "-m", "chore: initial fixture-repo commit for git-workspace-isolation example")

    print("fixture-repo initialized with initial commit.", flush=True)


def _micro_eval_command(repo_root: Path) -> list[str] | None:
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


def _run_step(
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


def _print_instructions(example_root: Path, args: argparse.Namespace) -> None:
    report_path = example_root / "report.html"
    print(
        f"""
Done. Static HTML report: {report_path}

What to observe in the outputs:
  1. git worktree isolation
     Each cell ran in an isolated git worktree under .micro-eval/workspaces/.
     Changes one cell makes do not affect other cells or fixture-repo itself.

  2. SameStartSnapshot (in run.json)
     Look for same_start_snapshot.fixture_digests — SHA-256 of fixture-repo HEAD.
     Look for same_start_snapshot.toolchain_fingerprint — python3 + requirements.txt hash.
     These prove both runs started from the same code and dependency state.

  3. OS policy sandbox
     Look for same_start_snapshot.sandbox_policy in run.json.
     On macOS: "seatbelt" (if available). On Linux: "bubblewrap" (if available).
     If neither is available, the value is "logical" with a caveat noting the downgrade.

  4. Drift breakpoint (trend analysis)
     Two runs were recorded: v1 (timeout_s=60) and v2 (timeout_s=120).
     The config digest differs between the runs, which triggers a drift caveat.
     This marks a breakpoint in the trend chart — results before/after are not
     directly comparable due to the configuration change.

     To inspect trends via API (after launching the UI):
       curl http://localhost:{args.port}/api/trends?config_id=refactor-agent-v1

  5. Human annotation (optional)
     Launch the UI with: python {Path(__file__).name} --ui
     Open http://localhost:{args.port}/run/<run_id>
     Use the AnnotationPanel to add a human score and comment to any cell.
     Refresh and re-run the text report to see the annotation included.
""",
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
