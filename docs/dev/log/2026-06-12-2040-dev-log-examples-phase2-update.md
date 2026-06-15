---
title: Development Log - Examples Phase 2 Update
doc_type: dev_log
status: active
created_at: 2026-06-12T20:40+08:00
updated_at: 2026-06-12T20:40+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - examples
  - onboarding
  - phase2
related:
  - docs/bug_reports/2026-06-12-2010-examples-phase2-gap.md
  - examples/agent-codefix-showdown/README.md
---

# Development Log - Examples Phase 2 Update

## Summary

Closed the examples gap from
`docs/bug_reports/2026-06-12-2010-examples-phase2-gap.md`: the
agent-codefix-showdown example now demonstrates Phase 2 capabilities on the
zero-cost deterministic mock path.

## Changes

- `eval.mock.yaml`: repetitions 1 → 3 so the smoke run produces real
  pass@k/pass^k aggregation with no `low_sample` caveat; process trace
  capture enabled; disabled `judge:` block added with enablement guidance.
- `eval.yaml` (real-agent matrix): disabled `trace:`/`judge:` example blocks
  only; repetitions unchanged to avoid real LLM token spend.
- Both READMEs: new "What Phase 2 adds to this smoke run" section (pass@k,
  decision.json location, TraceRef/cost source semantics, review page URL,
  judge-never-overrides-deterministic note); use-case description refreshed.

## Verification

- `python examples/run-example.py` exit 0; latest run's decision.json shows
  `pass_at_k {1,2,3} = 1.0`, empty stats caveats, 3 process TraceRefs.
- `micro-eval validate` passes for both YAML files.
- `uv run pytest -q`: 122 passed.

## Security Checklist

- No secrets added to example YAML, prompts, or fixtures; judge/trace blocks
  reference env-var credential flows only.
- Workspace boundary and shell interpolation: unchanged (config/docs only).
