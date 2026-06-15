---
title: Decision - Phase 2 P2-d LLM Judge Initial Design
doc_type: decision
status: active
created_at: 2026-06-12T12:16+08:00
updated_at: 2026-06-12T12:16+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - phase2
  - llm-judge
  - deepeval
  - decision
related:
  - docs/superpowers/plans/2026-06-12-phase2-implementation-plan.md
  - docs/superpowers/specs/2026-06-02-unicorn-design.md
  - docs/engineering/security-guidelines.md
---

# Decision - Phase 2 P2-d LLM Judge Initial Design

## Decision

Implement P2-d as an optional `judge:` pipeline that appends supplemental `EvaluationResult` records and `judge_rationale` evidence after deterministic validation. The judge is default-off, mockable in tests, and must not override deterministic validation failure in verdict-relevant cell state.

## Context

Unicorn Design §4.4.3 defines Mode 3 calibrated rubric as expert-calibrated LLM judgment. The Phase 2 implementation plan marks DeepEval custom metric as a stretch goal and requires a small judge prompt/rubric mapping design before code.

## Prompt and rubric mapping

The initial prompt maps task data into a structured judge input:

- task name and description;
- task input payload excerpt;
- expected output, when present;
- rubric text or rubric dimensions, when present;
- agent output summary/stdout summary/stderr summary;
- deterministic validation result and evidence summaries.

The judge must return a bounded result:

```json
{
  "score": 0.0,
  "pass_fail": "fail",
  "rationale": "short reason grounded in rubric and evidence",
  "scores": {"overall": 0.0}
}
```

Rubric handling for this initial slice:

1. If a task has `rubric.text`, use it as the primary judging criteria.
2. If a task has `rubric.dimensions`, include each dimension as a scoring axis.
3. If no rubric exists, the judge may score only general task alignment and must mark rationale as low-confidence.
4. Calibration samples are not loaded yet; this is an adapter seam for future Mode 3 calibration, not the full calibrated workflow.

## Options considered

1. Direct DeepEval runner integration.
   - Rejected for now: the project decision says DeepEval is only a scoring library, not the runner.
2. Hard dependency on DeepEval.
   - Rejected: P2-d must be optional and default-off.
3. Local protocol with optional DeepEval-backed implementation.
   - Chosen: keeps tests offline, avoids SDK drift in core engine, and preserves the EvaluationResult contract.

## Security and safety rules

- Judge API keys must use existing `MICRO_EVAL_SECRET_*` declaration/injection conventions or provider-specific environment variables read by the optional SDK, never eval.yaml.
- Judge rationale is persisted only after `Redactor.redact()`.
- Judge failures degrade to no judge result; they do not fail the run.
- Deterministic validation failure remains authoritative for `CellResult.pass_fail`, `CellResult.status`, and guarded decision behavior. Judge output is supplemental evidence unless a future human override flow is explicitly designed.

## Consequences

- The first implementation can be tested with a fake judge and without network.
- Future DeepEval SDK-specific code remains isolated in `evaluation/llm_judge.py`.
- Full Mode 3 calibration needs a later task package/calibration sample format.
