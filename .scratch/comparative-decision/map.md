---
title: LOCAL-COMPARATIVE-DECISION — Comparative decision workstream map
doc_type: reference
status: active
created_at: 2026-08-29T18:09+08:00
updated_at: 2026-08-29T18:09+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - work-record
  - workstream-map
related:
  - docs/agents/issue-tracker.md
  - src/micro_eval/decision/summary.py
---

# LOCAL-COMPARATIVE-DECISION — Comparative decision workstream map

## Scope

Evidence-protected semantics and artifacts for comparing baseline and
candidate configurations, including task-level direction, run verdicts,
confidence, caveats, and their report/UI projections.

## Boundaries

Execution providers, benchmark adoption, acquisition demos, release mechanics,
and aggregation work unrelated to a comparative verdict belong elsewhere.
Multiple-candidate ranking remains outside the first ticket until the
two-configuration contract is stable.

## Decisions-so-far

- `LOCAL-COMPARATIVE-DECISION-01` — [让单 baseline/candidate run 给出可审计的比较结论](issues/01-emit-comparative-verdict.md)
