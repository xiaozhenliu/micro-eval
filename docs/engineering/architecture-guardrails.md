---
title: "micro-eval Architecture Guardrails"
language: en
authoritative: true
date: 2026-06-02
updated_at: 2026-09-27T16:00+08:00
status: draft
type: engineering-guidelines
tags:
  - engineering
  - architecture
  - micro-eval
---

# micro-eval Architecture Guardrails

This document turns the Unicorn architecture invariants into engineering implementation boundaries. Architectural facts follow Part I of `docs/superpowers/specs/2026-06-02-unicorn-design.md`.

## Decision loop

Implementation code must serve the Unicorn decision loop:

```text
Task Authoring -> Evaluation Contract -> Command Adapter -> Same-start
  -> Run (Tasks x Configurations x Repetitions) -> Evidence Chain
  -> Basic Honest Stats -> Decision Report
```

Once the loop breaks, the product regresses to "dump a pile of results and let the user guess". That is not micro-eval.

## Non-breakable engineering boundaries

| Boundary | Engineering implication |
|---|---|
| MVP is a Profile, not a fork | The MVP may be a low-configuration implementation, but it must not create a data model incompatible with Unicorn. |
| Run = Tasks x Configurations x Repetitions | baseline / candidate are roles only, never the core object structure. |
| Agent is a black box behind adapters | The Execution Kernel does not know concrete agent command details; it only calls the Adapter contract. |
| Environment is part of input | workspace / commit / config / toolchain enter the snapshot or replay identity. |
| Evidence before decision | Decision may only reference Evaluation + Evidence; it never interprets raw stdout directly. |
| Deterministic checks before LLM judgment | When test / lint / exit code / schema can decide, do not hand the call to an LLM judge first. |
| Secrets are never evidence | Secrets never enter artifacts, traces, judge prompts, reports, or UI responses. |
| Stable IDs + schema_version are mandatory | Cross-module objects must carry stable IDs and a schema version. |

If an implementation wants to bypass these boundaries, change Unicorn / the MVP profile first instead of quietly opening exceptions in code.

## Dependency direction

- Configuration reads Asset.
- Execution reads RunPlan.
- Agent Adapter and Environment serve Execution.
- Artifact / Trace record facts.
- Evaluation reads Evidence and scores.
- Decision reads Evaluation + Evidence and concludes.
- The UI is the presentation of the Decision layer; it does not interpret raw stdout directly.

## Forbidden shortcuts

- The UI infers a winner straight from stdout.
- The Kernel creates verdicts.
- An Adapter decides whether a task passes.
- A Scorer creates workspaces.
- A Route Handler bypasses RunStore and assembles paths to read or write results.
- The legacy baseline/candidate model keeps expanding as the base for new features.
