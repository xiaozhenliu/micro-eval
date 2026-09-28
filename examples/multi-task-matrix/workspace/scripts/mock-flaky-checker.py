#!/usr/bin/env python3
"""Deterministic mock checker that intentionally fails the generate-report task.

Task routing: same as mock-good-checker EXCEPT for "report":
  - "style" in prompt  => exit 0 (PASS — same as good checker)
  - "bug" in prompt    => BUG_FOUND + bugs-report.txt in output_dir (PASS — same as good checker)
  - "report" in prompt => writes output file but DOES NOT create report/summary.json
                          => command expectation fails => mixed decision for this config

Files that must survive for validation must go into MICRO_EVAL_OUTPUT_DIR.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: mock-flaky-checker.py <output_file>", file=sys.stderr)
        return 2

    output_file = Path(sys.argv[1]).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Artifact output directory that persists after workspace cleanup.
    output_dir = Path(os.environ.get("MICRO_EVAL_OUTPUT_DIR", output_file.parent)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt = sys.stdin.read()

    if "style" in prompt.lower():
        return handle_style(output_file)
    if "bug" in prompt.lower():
        return handle_bugs(output_file, output_dir)
    if "report" in prompt.lower():
        return handle_report_flaky(output_file)

    output_file.write_text("# mock-flaky-checker\nSTATUS=PASS\n")
    return 0


def handle_style(output_file: Path) -> int:
    """Handle check-style task: exit 0 (same result as good checker)."""
    output_file.write_text(
        "# mock-flaky-checker style result\n\n"
        "STYLE_CHECK=PASS\n"
        "issues_found=0\n"
    )
    return 0


def handle_bugs(output_file: Path, output_dir: Path) -> int:
    """Handle find-bugs task: report bug, create bugs-report.txt in output_dir."""
    bugs_path = output_dir / "bugs-report.txt"
    bugs_path.write_text(
        "# Bug Report — mock-flaky-checker\n\n"
        "## BUG-1: Off-by-one in process_data\n"
        "File: workspace/sample-project/main.py, line 20\n"
        "range(len(items) - 1) skips the last element.\n"
        "Severity: high\n"
    )
    output_file.write_text(
        "# mock-flaky-checker bug-find result\n\n"
        "BUG_FOUND: off-by-one in process_data (main.py:20)\n"
        "bugs_found=1\n"
        f"report={bugs_path}\n"
    )
    return 0


def handle_report_flaky(output_file: Path) -> int:
    """Handle generate-report task: write output but skip creating report/summary.json.

    This intentional omission causes the command expectation
    `python3 -c "import json; json.load(open('report/summary.json'))"` to fail
    with a FileNotFoundError, making this cell a FAIL.
    """
    output_file.write_text(
        "# mock-flaky-checker report result\n\n"
        "STATUS=INCOMPLETE\n"
        "Note: report generation skipped — demonstrating a partial failure "
        "that triggers caveat and mixed decision.\n"
    )
    # Intentionally does NOT create report/summary.json.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
