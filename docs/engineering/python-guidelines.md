---
title: "micro-eval Python Guidelines"
language: en
authoritative: true
date: 2026-06-02
updated_at: 2026-09-27T16:00+08:00
status: draft
type: engineering-guidelines
tags:
  - engineering
  - python
  - micro-eval
---

# micro-eval Python Guidelines

Scope: `src/micro_eval/` and the Python tests.

## Language and Runtime

- Python 3.11+.
- Package management: prefer `uv`.
- CLI: Typer.
- Data models: Pydantic v2.
- Output: Rich is fine for human-facing CLI output; machine-readable output must be structured JSON.

## Code Style

- Function signatures carry type annotations.
- Dataclasses / Pydantic models may be used inside a module; cross-module JSON prefers Pydantic models.
- Paths use `pathlib.Path`.
- Timestamps use explicit formats; timestamps that enter IDs use the compact format to avoid clashing with `::`.
- Error types must be distinguishable, e.g. config error, adapter error, workspace error, store error.
- Code comments must be in English.

Avoid:

- Passing domain objects between modules as bare dicts.
- Assembling `.micro-eval/runs/...` inside business code.
- Calling `asyncio.create_subprocess_shell` directly.
- Using a display name as a stable ID.
- Catching broad exceptions and swallowing the error.

## Async and Subprocess

- Agent execution is I/O bound; use asyncio.
- Concurrency must be governed by `max_concurrency`.
- Each RunCell's timeout is handled individually.
- On timeout, terminate first, then escalate to kill.
- A single cell failure must not block other cells unless the RunPlan's guardrails explicitly require stopping.

## Safe Subprocess Checklist

Every new subprocess call must answer:

- Where does the input come from?
- Does it pass through a shell?
- Do stdout / stderr have a size cap?
- Could secrets leak?
- How is the child terminated after a timeout?
- Does the failure affect other cells?

Default requirements:

- Use an argv list.
- No shell string interpolation.
- Task input is passed via stdin or a file.
- Output files / directories are declared through explicit environment variables or arguments.
- Timeout, output cap, and artifact size cap must come from guardrails or default values.
- stdout / stderr must pass redaction before persistence.

## Pydantic Models

- Every cross-module object carries `schema_version`.
- Enums use explicit strings; complex state is never expressed with implicit bools.
- Optional fields have explicit semantics: unknown, not applicable, and not collected must not be conflated.
- Digest fields must state their input material and where the canonicalization rules are documented.
- Serialized model output must be covered by contract tests.
