---
title: Development Log - v0.2.0 Docs and Release Prep
doc_type: dev_log
status: active
created_at: 2026-06-12T12:49+08:00
updated_at: 2026-06-12T12:49+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - release
  - docs
  - phase2
related:
  - CHANGELOG.md
  - README.md
  - README.zh-CN.md
  - docs/DEVELOPMENT.md
  - micro-eval-prd.md
  - docs/releases/2026-06-12-v0.2.0-release-evidence.md
---

# Development Log - v0.2.0 Docs and Release Prep

## Summary

Prepared Phase 2 documentation and release metadata for version `0.2.0` without committing, tagging, pushing, or publishing to `main`.

## Context

After completing Phase 2 implementation slices for aggregation, trace capture, review UI, and optional LLM judge, project-facing documentation still described the 0.1.3 MVP state. Release prep needed the version surfaces, changelog, README, development guide, PRD snapshot, release evidence, and dependency inventory to match the current codebase.

## Changes

- Synced version surfaces to `0.2.0` with the project release script.
- Updated README and Chinese README to describe Phase 2 aggregation, `decision.json`, trace, cost, review UI, and default-off LLM judge behavior.
- Updated `docs/DEVELOPMENT.md` module map, canonical flow, release references, and trace/judge safety notes.
- Added current `trace` and `judge` sections to `eval.yaml.example`.
- Added `CHANGELOG.md` section for `0.2.0`.
- Created development-only `micro-eval-prd.md` to reflect the current Phase 2 product scope.
- Generated `docs/releases/2026-06-12-v0.2.0-dependency-inventory.{md,json}`.
- Created `docs/releases/2026-06-12-v0.2.0-release-evidence.md`.

## Decisions

- Use `0.2.0` as the Phase 2 release version because the work adds L2 aggregation, trace, review, and optional judge capabilities beyond the 0.1.x MVP line.
- Keep PRD as a dev-only root document, consistent with release rules that exclude `micro-eval-prd.md` from `main`.
- Do not commit or publish release artifacts until explicitly requested.

## Verification

- `.codex/skills/micro-eval-release/scripts/check-version-consistency.py --version 0.2.0` — pass.
- `.codex/skills/micro-eval-release/scripts/preflight-release.sh 0.2.0` — pass.
- `uv run python examples/run-example.py` — pass; latest smoke run recorded tool version `0.2.0`, `decision.json`, one trace, and one evaluation file.
- `grep -RIn "import deepeval\|import langfuse" src/micro_eval/engine src/micro_eval/evaluation src/micro_eval/trace || true` — no direct SDK imports in trusted implementation paths.

## Risks and follow-ups

- `micro-eval-prd.md` is gitignored by design. If maintainers want it committed on `dev`, it must be added intentionally with `git add -f` and still excluded from `main` during release projection.
- Release commit, tag, and dev-to-main publication remain pending explicit approval.
