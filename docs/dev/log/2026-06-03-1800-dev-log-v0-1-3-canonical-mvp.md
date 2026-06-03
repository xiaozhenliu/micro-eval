---
title: Development Log - v0.1.3 Canonical MVP
doc_type: dev_log
status: active
created_at: 2026-06-03T18:00+08:00
updated_at: 2026-06-03T18:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - v0.1.3
  - canonical-mvp
  - release
related:
  - CHANGELOG.md
  - docs/releases/2026-06-02-mvp-release-evidence.md
  - docs/DEVELOPMENT.md
  - docs/superpowers/specs/2026-06-02-mvp-profile.md
---

# Development Log - v0.1.3 Canonical MVP

## Summary

Promoted the MVP to the canonical `tasks × configurations × repetitions` execution model with guarded decisions, persistent human evaluation, canonical run storage, and manifest-backed artifacts.

## Context

The project needed to move from a useful baseline/candidate prototype to a reproducible evaluation workbench where conclusions can be traced back to tasks, configs, evidence, artifacts, and same-start snapshots.

## Changes

- Added canonical `RunPlan`, `RunCell`, Pydantic contracts, and matching TypeScript/zod contracts.
- Added `micro-eval init`, `validate`, `run`, `list`, `report`, and `ui` as the local Golden Path.
- Added `.micro-eval/runs/{run_id}/` canonical storage with `run.json`, `manifest.json`, cell results, text artifacts, and append-only `evaluation.json` records.
- Added same-start and replay evidence through snapshots and guarded decision reporting.
- Added managed workspaces for `blank`, `files`, and `git_repo` tasks.
- Added deterministic validators and persistent human evaluation through the Next.js API/UI.
- Added artifact viewer, static reports, starter templates, and deterministic dogfood coverage.
- Aligned `VERSION`, Python runtime `__version__`, UI package lock metadata, and `ReplayCanonical.tool_version` on `0.1.3`.

## Decisions

- Use guarded decisions that can return `not_comparable` or `inconclusive` instead of overstating a winner.
- Persist human evaluation as append-only evidence rather than browser-local state.
- Keep DeepEval, Langfuse, and OpenHands integration boundaries aligned with the MVP roadmap rather than over-expanding the release.
- Keep historical `0.1.0` / `0.1.1` / `0.1.2` references in changelog, dev logs, archive, and specs unchanged because they describe past release states rather than current runtime version.

## Verification

Release history records the following release gate evidence:

- `uv run python -m compileall src/micro_eval tests`
- `uv run pytest -q` with latest release gate `67 passed`
- `cd ui && npm run lint && npm run build`
- `uv build`
- Wheel smoke test with Python `>=3.11`
- `git diff --check`
- Security greps for shell execution and browser storage risks
- Independent code review: `APPROVE`
- Independent architecture review: `CLEAR`
- UltraQA adversarial MVP smoke: `PASS`

## Risks and follow-ups

- Langfuse remains optional/future work.
- DeepEval is reserved for scoring-library integration and is not used as a test runner.
- OpenHands sandbox integration, multi-team collaboration, RBAC/SSO, large-scale task libraries, and recommendation engines remain out of MVP scope.
