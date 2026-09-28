#!/usr/bin/env python3
"""Deterministic test-local "solver" agent for the starter-tasks template.

Not shipped with micro-eval. Used only by
tests/integration/test_starter_tasks_run.py to prove the starter-tasks
template's files-workspace copy, validator cwd resolution, and
command-expectation exit-code judging work end to end through the real
CLI `run` command, without any real agent, model call, or network access.

Reads the task prompt from stdin (agent input_mode: stdin), identifies
which starter task it is being asked to fix by looking for that task's
id in the prompt text, then copies the known-good solution module for
that task from tests/fixtures/starter_tasks_solutions/<task-id>/ into the
copied fixture directory under the current working directory (which is
the agent's cwd, i.e. the prepared cell workspace root).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# tests/integration/support/starter_tasks_solver.py -> tests/
SOLUTIONS_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "starter_tasks_solutions"

TASK_MODULES = {
    "date-range-overlap": "date_range_overlap.py",
    "csv-quoted-fields": "csv_quoted_fields.py",
    "lru-cache-order": "lru_cache_order.py",
    "slugify-hyphens": "slugify_hyphens.py",
    "page-bounds": "page_bounds.py",
}


def main() -> int:
    prompt = sys.stdin.read()
    cwd = Path.cwd()

    matched_task_id: str | None = None
    for task_id in TASK_MODULES:
        if task_id in prompt:
            matched_task_id = task_id
            break

    if matched_task_id is None:
        print("solver: could not identify a starter task in the prompt", file=sys.stderr)
        return 1

    module_name = TASK_MODULES[matched_task_id]
    solution = SOLUTIONS_ROOT / matched_task_id / module_name
    destination = cwd / matched_task_id / module_name

    if not solution.exists():
        print(f"solver: missing solution file {solution}", file=sys.stderr)
        return 1
    if not destination.parent.exists():
        print(f"solver: expected fixture directory missing: {destination.parent}", file=sys.stderr)
        return 1

    shutil.copy2(solution, destination)
    print(f"applied fix for {matched_task_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
