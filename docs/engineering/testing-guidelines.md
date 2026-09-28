---
title: "micro-eval Testing Guidelines"
language: en
authoritative: true
date: 2026-06-02
updated_at: 2026-09-27T16:00+08:00
status: draft
type: engineering-guidelines
tags:
  - engineering
  - testing
  - micro-eval
---

# micro-eval Testing Guidelines

The authoritative source for the test architecture is `docs/superpowers/specs/2026-06-02-test-architecture.md`. This document only adds engineering execution principles.

## Test Types

- Unit: pure functions, schemas, IDs, digests, redaction.
- Contract: Pydantic / zod parity; golden JSON.
- Integration: Kernel + Adapter + Workspace + Store.
- E2E: CLI `run` -> result files -> `report`.
- UI: API routes, ResultMatrix, ArtifactViewer, EvaluationPanel.

## What Must Be Tested

Every "must not bypass" rule gets a negative test.

Minimum test list:

- Shell string interpolation is rejected.
- The Kernel invokes agents through the Adapter.
- EvaluationResults reference EvidenceItems.
- Strong DecisionStatus conclusions reference evaluation / evidence.
- Snapshot mismatch degrades the conclusion.
- Secrets never appear in artifacts, evidence, reports, or UI responses.
- Pydantic / zod schemas stay aligned.

## No Flaky Tests

- Regular tests never call real LLMs.
- Regular tests never depend on external networks.
- Subprocesses use mock agents / fixture scripts.
- Git workspace tests use small fixture repos.
- Time and randomness stay controllable.
