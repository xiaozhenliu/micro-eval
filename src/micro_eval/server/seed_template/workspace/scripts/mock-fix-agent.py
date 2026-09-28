#!/usr/bin/env python3
"""Deterministic local fixer for the example smoke path."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TEST_TIMEOUT_S = 60
FIXED_LEDGER = '''"""Tiny ledger allocation module used by the micro-eval example."""

from __future__ import annotations


def split_amount_cents(total_cents: int, weights: list[int]) -> list[int]:
    """Split total cents across positive integer weights."""
    if total_cents < 0:
        raise ValueError("total_cents must be non-negative")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(weight <= 0 for weight in weights):
        raise ValueError("weights must be positive")

    total_weight = sum(weights)
    raw_shares = [(total_cents * weight, index) for index, weight in enumerate(weights)]
    base = [numerator // total_weight for numerator, _index in raw_shares]
    remainder = total_cents - sum(base)
    remainder_order = sorted(
        range(len(weights)),
        key=lambda index: (raw_shares[index][0] % total_weight, -index),
        reverse=True,
    )
    for index in remainder_order[:remainder]:
        base[index] += 1
    return base
'''


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: mock-fix-agent.py <output_file>", file=sys.stderr)
        return 2
    output_file = Path(sys.argv[1]).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    repo_dir = Path(__file__).resolve().parents[1]
    _prompt = sys.stdin.read()

    (repo_dir / "ledger.py").write_text(FIXED_LEDGER)
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=repo_dir,
        text=True,
        capture_output=True,
        timeout=TEST_TIMEOUT_S,
        check=False,
    )
    status = "PASS" if result.returncode == 0 else "FAIL"
    output_file.write_text(
        "# micro-eval mock fixer result\n\n"
        "This is MVP smoke/use-case validation, not a benchmark-quality winner signal.\n\n"
        "agent_target=mock-local\n"
        f"unit_test_exit_code={result.returncode}\n"
        f"MICRO_EVAL_TASK_RESULT={status}\n\n"
        "## Unit test stdout\n\n"
        f"{result.stdout}\n\n"
        "## Unit test stderr\n\n"
        f"{result.stderr}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
