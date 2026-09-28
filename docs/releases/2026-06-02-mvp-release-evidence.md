---
title: MVP Release Evidence
doc_type: release_evidence
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-06-03T08:42+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - release
  - evidence
  - mvp
  - verification
related:
  - docs/DEVELOPMENT.md
  - docs/documentation-standard.md
  - docs/superpowers/specs/2026-06-02-mvp-profile.md
---

# MVP Release Evidence — 2026-06-02

This document records the release-readiness evidence expected before merging the MVP branch.

## Scope

Completed MVP phases:

- P0-a canonical execution skeleton
- P0-b reproducibility evidence and read-only canonical UI/API
- P1 append-only human evaluation and decision recomputation
- P2 local workflow hardening
- P3 release readiness and final quality gate

## Golden Path Evidence

The deterministic dogfood test `tests/e2e/test_mvp_dogfood_cli.py` covers:

1. `micro-eval init --force`
2. `micro-eval validate --format json`
3. `micro-eval run --dry-run --format json`
4. `micro-eval run --max-concurrency 2 --format json`
5. `micro-eval list --format json`
6. `micro-eval report --format json`

Expected evidence fields:

- `same_start_snapshot`
- `replay_canonical`
- per-cell `cell_snapshot`
- per-cell `snapshot_gate_result`
- starter templates under `tasks/templates/`

## Required Verification Commands

```bash
uv run python -m compileall src/micro_eval tests
uv run pytest -q  # latest: 67 passed
cd ui && npm run lint && npm run build
uv build
git diff --check
grep -R "create_subprocess_shell" src tests ui || true
grep -R "shell=True" src tests ui || true
grep -R "localStorage" ui/src || true
```

## Security Checklist

- Shell interpolation: canonical subprocess and validation commands are argv-only.
- Secrets redaction: all host `MICRO_EVAL_SECRET_*` values are used for redaction, while only declared `required_secrets` are injected into agent env.
- Workspace boundary: agent cwd is the assigned blank/files/git worktree workspace; setup env is allowlisted and does not inherit `MICRO_EVAL_SECRET_*`.
- Raw artifact exposure: UI/API exposes text content only through explicit manifest `artifact_id` lookup, constrained by run-dir `realpath`; symlink/linked, binary, and oversized artifacts are skipped or returned as placeholders with warnings.
- Snapshot mismatch: decision stays guarded and downgrades to `not_comparable` / `inconclusive`.

## Final Quality Gate

Before final checkpoint, run and record:

- ai-slop-cleaner on changed files
- independent code-reviewer review
- independent architect review
- ultraqa/adversarial MVP smoke
