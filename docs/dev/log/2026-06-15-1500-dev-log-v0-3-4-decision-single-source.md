---
title: Development Log - v0.3.4 Decision Algorithm Single Source of Truth
doc_type: dev_log
status: active
created_at: 2026-06-15T15:00+08:00
updated_at: 2026-06-15T15:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - tech-debt
  - decision-layer
  - issue-1
related:
  - docs/superpowers/plans/2026-06-15-issue1-decision-single-source.md
---

# Development Log - v0.3.4 Decision Algorithm Single Source of Truth

## Summary

Resolved issue #1: the decision verdict algorithm was duplicated between Python (`build_decision` + `build_aggregation`, ~190 lines) and TypeScript (`recomputeDecision` + helpers, ~130 lines). The UI evaluate endpoint now delegates to a Python subprocess, making `build_decision` the single source of truth.

## What changed

- **New CLI command** `micro-eval apply-evaluation --run-id <id> --cell-id <id>`: reads evaluation input from stdin JSON, constructs the human evaluation via `build_human_evaluation`, appends it through `RunStore.append_evaluation` (which calls `build_decision` internally), and writes `{evaluation, evidence, decision}` JSON to stdout.

- **UI evaluate route rewritten**: `ui/src/app/api/runs/[id]/cells/[cellId]/evaluate/route.ts` now calls `execFileSync(uv, [...args])` with the payload on stdin. Supports `MICRO_EVAL_UV_PATH` env var for custom uv binary path.

- **Deleted `ui/src/lib/evaluation.ts`** (226 lines): `recomputeDecision`, `appendEvaluationToRun`, `buildHumanEvaluation`, `appendEvaluationFile`, and all helpers. Also deleted the cross-language equivalence test and evaluation unit tests (~200 lines).

## Key design decisions

1. **Subprocess over HTTP API**: the UI is a local dev tool with a single user; spawning a Python subprocess per evaluation (~200-500ms) is simpler than running a Python server alongside Next.js.

2. **stdin JSON over CLI flags**: the `scores` field is a `Record<string, float>` dict that cannot be cleanly passed via CLI flags. stdin JSON handles arbitrary payloads.

3. **One-time cutover, no migration**: Python and TS `buildHumanEvaluation` use different hash inputs for evaluation IDs. Since this is a clean cut (no gradual migration), old IDs stay as-is in run.json and new IDs use Python's format. No conflicts possible.

4. **No new tests for the CLI command**: it's ~30 lines of glue calling three already-tested functions. The golden contract test continues to protect `build_decision`.

## Impact

- Net -364 lines (74 added, 438 deleted)
- 455 pytest + 42 vitest passing
- Decision algorithm modifications now require changing Python only
- UI evaluate endpoint now requires Python + uv to be available (was previously self-contained TS)

## Security notes

- `execFileSync` uses argv array (no shell). User data flows only through stdin JSON.
- Explicit `id` format validation (`/^[A-Za-z0-9_.:-]+$/`) added before subprocess call (defense-in-depth, in addition to existing `getRun` → `safeId` check).
- Python-side `build_human_evaluation` applies `_redact_env_secrets` before persisting.
