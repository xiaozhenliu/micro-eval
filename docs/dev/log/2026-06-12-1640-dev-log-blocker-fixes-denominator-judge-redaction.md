---
title: Development Log - Blocker Fixes (denominator_policy + Judge Prompt Redaction)
doc_type: dev_log
status: active
created_at: 2026-06-12T16:40+08:00
updated_at: 2026-06-12T16:40+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - bugfix
  - security
  - evaluation
related:
  - docs/bug_reports/2026-06-12-1521-dev-branch-review-findings.md
  - docs/engineering/security-development-guidelines.md
---

# Development Log - Blocker Fixes (denominator_policy + Judge Prompt Redaction)

## Summary

Fixed the two blocker defects from the dev-branch review report
(`docs/bug_reports/2026-06-12-1521-dev-branch-review-findings.md`):

1. `evaluation.denominator_policy` was parsed and hashed but never used by
   aggregation (Python or UI).
2. The LLM judge prompt was sent to external providers without redaction;
   only the returned rationale was redacted.

## Changes

### Fix 1 — denominator_policy end-to-end

- `src/micro_eval/models/run.py`: `RunPlan` and `RunRecord` carry
  `denominator_policy` (default `include_failed`, keeps old run.json compatible).
- `src/micro_eval/config/planner.py`: copies the policy from project config
  into the plan, so historical runs keep the semantics they ran with (P3).
- `src/micro_eval/store/run_store.py`: persists the policy into the record.
- `src/micro_eval/decision/summary.py`: `build_decision()` now passes
  `denominator_policy=record.denominator_policy` to `build_aggregation()`.
- `ui/src/lib/schema.ts` + `ui/src/lib/evaluation.ts`: zod schema field added;
  `recomputeDecision()` reads the run's policy and uses successful cells as
  the denominator under `exclude_failed`, matching the Python implementation.

### Fix 2 — judge prompt redaction

- `src/micro_eval/evaluation/llm_judge.py`: `build_judge_prompt()` takes a
  required `redactor` and redacts all external-origin fields (task description,
  input, expected output, rubric, agent output/stdout, stderr, validation
  comment, evidence summaries) **before** truncation, so secrets cannot escape
  as truncated fragments. `redactor` is required (not optional) so new callers
  cannot silently bypass redaction.

## Verification

- `uv run pytest -q`: 92 passed.
- `cd ui && npx vitest run`: all passed.
- New tests: `tests/unit/test_denominator_policy_e2e.py` (policy changes
  pass_rate as expected), redaction assertions in
  `tests/unit/test_llm_judge.py`, and
  `ui/src/lib/__tests__/evaluation.test.ts` for UI denominator behavior.

## Security Checklist

- Secrets redaction: enforced on the outbound judge prompt, redact-before-truncate.
- Workspace boundary: no new workspace writes.
- Shell interpolation: no subprocess changes.
