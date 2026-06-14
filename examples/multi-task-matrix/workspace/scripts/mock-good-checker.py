#!/usr/bin/env python3
"""Deterministic mock checker that succeeds on all three tasks.

Task routing: reads stdin prompt, identifies task by keyword, writes output file.

  - "style" in prompt  => exit 0, write STYLE_CHECK=PASS to output_file
  - "bug" in prompt    => write BUG_FOUND line to output_file,
                          create bugs-report.txt in MICRO_EVAL_OUTPUT_DIR
  - "report" in prompt => create report/summary.json in MICRO_EVAL_OUTPUT_DIR,
                          write REPORT_GENERATED to output_file

Files that must survive for validation (file_exists, command expectations) must go
into MICRO_EVAL_OUTPUT_DIR — the artifact output directory that persists after the
workspace is cleaned up. The workspace CWD is ephemeral.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: mock-good-checker.py <output_file>", file=sys.stderr)
        return 2

    output_file = Path(sys.argv[1]).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # MICRO_EVAL_OUTPUT_DIR is the artifact directory that persists after workspace cleanup.
    # Write durable artifacts (bugs-report.txt, report/) here so file_exists and
    # command expectations can find them after the workspace is removed.
    output_dir = Path(os.environ.get("MICRO_EVAL_OUTPUT_DIR", output_file.parent)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt = sys.stdin.read()

    if "style" in prompt.lower():
        return handle_style(output_file)
    if "bug" in prompt.lower():
        return handle_bugs(output_file, output_dir)
    if "report" in prompt.lower():
        return handle_report(output_file, output_dir)

    # Unknown task — write a generic pass and exit 0.
    output_file.write_text("# mock-good-checker\nSTATUS=PASS\n")
    return 0


def handle_style(output_file: Path) -> int:
    """Handle check-style task: exit 0, write pass status."""
    output_file.write_text(
        "# mock-good-checker style result\n\n"
        "STYLE_CHECK=PASS\n"
        "issues_found=0\n"
        "Note: bare except in main.py:load_csv and missing type annotations "
        "detected but below blocking threshold.\n"
    )
    return 0


def handle_bugs(output_file: Path, output_dir: Path) -> int:
    """Handle find-bugs task: report off-by-one, create bugs-report.txt in output_dir."""
    bugs_path = output_dir / "bugs-report.txt"
    bugs_path.write_text(
        "# Bug Report — mock-good-checker\n\n"
        "## BUG-1: Off-by-one in process_data\n"
        "File: workspace/sample-project/main.py, line 20\n"
        "range(len(items) - 1) skips the last element.\n"
        "Severity: high\n\n"
        "## BUG-2: Bare except in load_csv\n"
        "File: workspace/sample-project/main.py, line 38\n"
        "Silently swallows all exceptions including KeyboardInterrupt.\n"
        "Severity: medium\n"
    )
    output_file.write_text(
        "# mock-good-checker bug-find result\n\n"
        "BUG_FOUND: off-by-one in process_data (main.py:20)\n"
        "BUG_FOUND: bare except in load_csv (main.py:38)\n"
        "bugs_found=2\n"
        f"report={bugs_path}\n"
    )
    return 0


def handle_report(output_file: Path, output_dir: Path) -> int:
    """Handle generate-report task: create report/summary.json in output_dir."""
    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "generator": "mock-good-checker",
        "task": "generate-report",
        "findings": {
            "style_issues": 3,
            "bugs_confirmed": 2,
            "files_analyzed": ["main.py", "utils.py", "tests/test_main.py"],
        },
        "verdict": "NEEDS_FIXES",
    }
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    output_file.write_text(
        "# mock-good-checker report result\n\n"
        "REPORT_GENERATED\n"
        f"report_path={report_dir / 'summary.json'}\n"
        "status=ok\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
