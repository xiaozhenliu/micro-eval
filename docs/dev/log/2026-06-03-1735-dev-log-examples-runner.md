---
title: Development Log - Examples Runner
doc_type: dev_log
status: active
created_at: 2026-06-03T17:35+08:00
updated_at: 2026-06-03T18:14+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - examples
  - onboarding
related:
  - examples/run-example.py
  - examples/agent-codefix-showdown/README.md
  - docs/engineering/security-guidelines.md
---

# Development Log - Examples Runner

## Summary

Added a cross-platform Python entrypoint so users can run the source-checkout
example with one command instead of manually switching directories and repeating
CLI commands.

## Context

The previous README flow mixed repository-root commands with example-directory
report commands. It was verbose and easy to run against the wrong
`.micro-eval/runs` store. The example also used `python3`, which is not a stable
command name across Windows, macOS, and Linux environments.

## Changes

- Added `examples/run-example.py`.
- Added `{python}` command placeholder support in canonical and legacy runners.
- Moved runtime workspaces from system temporary directories to
  `.micro-eval/workspaces/{run_id}/{cell_id}/` under the current eval project.
- Updated example YAML and wrapper scripts to use the current Python
  interpreter instead of hardcoding `python3`.
- Updated English and Chinese onboarding docs.
- Ignored generated example `report.html` files.
- Updated development and security documentation for project-local workspaces and
  example smoke verification.

## Decisions

- Use Python as the primary convenience entrypoint instead of shell scripts so
  the same command works across common user platforms.
- Keep real local agent runs opt-in via `--real`.
- Keep subprocess calls argv-only.

## Verification

- `uv run python examples/run-example.py`
- `uv run python examples/run-example.py --skip-run`
- `uv run pytest -q` — 72 passed
- `uv run python -m compileall src/micro_eval tests examples/run-example.py examples/agent-codefix-showdown/workspace/scripts`
- `git diff --check`
- `grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples || true` — no matches
- Latest example smoke recorded
  `examples/agent-codefix-showdown/.micro-eval/workspaces/{run_id}/{cell_id}` as the
  cell workspace path and showed `exists_after_cleanup=False`.

## Risks and follow-ups

- The source-checkout example still requires either `uv`, an installed
  `micro-eval`, or a Python environment with project dependencies.
