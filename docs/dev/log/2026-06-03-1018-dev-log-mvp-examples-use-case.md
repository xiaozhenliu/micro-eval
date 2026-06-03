---
title: Development Log - MVP Examples Use Case
doc_type: dev_log
status: active
created_at: 2026-06-03T10:18+08:00
updated_at: 2026-06-03T11:29+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - examples
  - mvp
related:
  - examples/agent-codefix-showdown/README.md
  - docs/DEVELOPMENT.md
  - docs/engineering/security-guidelines.md
---

# Development Log - MVP Examples Use Case

## Summary

Added a source-checkout MVP example use case under `examples/agent-codefix-showdown/` so users can run a complete `micro-eval` flow without preparing their own config, task, or fixture workspace.

## Context

The current MVP was complete but lacked a ready-to-run user path. The approved plan kept the example source-first rather than adding packaged wheel assets or a new `init --example` command.

## Changes

- Added `examples/README.md` as the examples index.
- Added `examples/agent-codefix-showdown/` with:
  - real-agent `eval.yaml` for Claude Code, Codex CLI, OpenClaw, and Hermes;
  - deterministic `eval.mock.yaml` for local smoke validation;
  - one task YAML for a ledger rounding bugfix;
  - copied workspace fixture and argv-only wrapper scripts.
- Added a top-level README entry for the ready-to-run example.

## Decisions

- Treat the example marker as MVP smoke/use-case validation, not a benchmark-quality winner signal.
- Keep real-agent wrappers as source examples and document local CLI auth/network caveats.
- Use `files` workspace to avoid nested Git setup for first-run onboarding.

## Verification

- `uv run micro-eval validate --config examples/agent-codefix-showdown/eval.yaml --format json`
- `uv run micro-eval validate --config examples/agent-codefix-showdown/eval.mock.yaml --format json`
- `uv run micro-eval run --config examples/agent-codefix-showdown/eval.mock.yaml --max-concurrency 1 --format json`
- `(cd examples/agent-codefix-showdown && uv run --project ../.. micro-eval list --format json)`
- `(cd examples/agent-codefix-showdown && uv run --project ../.. micro-eval report --format text)`
- `(cd examples/agent-codefix-showdown && uv run --project ../.. micro-eval report --format html --output report.html && test -f report.html)`
- `python3 -m compileall -q examples/agent-codefix-showdown/workspace/scripts examples/agent-codefix-showdown/workspace/tests`
- `git diff --check`
- source grep for `create_subprocess_shell` and `shell=True`

## Code review remediation

Independent code review found that the Claude wrapper path could persist task text in the recorded `agent_command`, and the architecture lane flagged the nested real-agent subprocess env boundary as a WATCH item. The remediation kept the wrapper example-only, added target-aware command redaction, replaced broad child env inheritance with a named allowlist, and documented argv prompt / limited env caveats in the example README.

## Final review and QA gate

- Code-review gate: `recommendation: APPROVE`, with no critical/high/medium/low issues reported.
- Architecture gate: `Architectural Status: CLEAR`; the previous env-boundary WATCH item was resolved by explicit child env allowlisting and target-aware redaction.
- UltraQA evidence covered real config validation, mock config validation, deterministic mock run, example-directory list/report/HTML report, run-agent redaction/env smoke, README caveat checks, whitespace diff check, shell-subprocess safety grep, and generated report cleanup.
- Runtime artifacts generated during QA remain ignored under `examples/agent-codefix-showdown/.micro-eval/` and Python `__pycache__/` directories.

## Risks and follow-ups

- Current examples are not wheel-bundled assets; pure wheel users still need a source checkout or a future packaged example/init command.
- Current UI still depends on source checkout UI assets.
- Future work can add first-class workspace diff artifacts for richer codefix evaluation evidence.
