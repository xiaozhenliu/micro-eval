---
title: "micro-eval Implementation Principles"
language: en
authoritative: true
date: 2026-06-02
updated_at: 2026-09-27T16:00+08:00
status: draft
type: engineering-guidelines
tags:
  - engineering
  - implementation
  - micro-eval
---

# micro-eval Implementation Principles

This document defines the general trade-offs when implementing code. Fields, module contracts, and MVP scope follow Unicorn and the MVP profile.

## Schema First

Define the schema for a cross-module object before writing the business flow.

- The Python side uses Pydantic v2.
- The TypeScript side uses zod.
- Field names, enums, nullability, and defaults of the same object must stay aligned across languages.
- Adding or changing cross-language JSON requires a contract test.
- A legacy schema must be explicitly marked legacy; it must never masquerade as a canonical schema.

Do not let the UI infer semantics from "JSON fields that happen to exist". The UI only consumes structures the schema acknowledges.

## Boundary First

Define the module interface before filling in the implementation.

- The Configuration layer produces the RunPlan.
- The Execution Kernel consumes the RunPlan and produces factual execution results.
- The Agent Adapter owns command invocation and I/O normalization.
- The Environment layer owns workspaces and snapshots.
- The Artifact / Trace layer stores raw artifacts and structured evidence.
- The Evaluation layer produces scores and validation results.
- The Decision layer produces verdicts, caveats, and recommended actions.

## Store Behind Interfaces

Data reads and writes must go through store abstractions; `.micro-eval/` paths must not be scattered through business logic.

Minimum requirements:

- On the Python side, runs, cells, artifacts, and evaluations are read and written through RunStore / ArtifactStore-style interfaces.
- On the UI/API side, data exposed by RunStore is read through a unified data access layer.
- File paths are computed from an injected base path or project root.
- JSON files are the MVP storage implementation, not a direct dependency of business modules.

`store/sqlite_store.py` already exists as an index layer (for query scenarios such as trend analysis) while JSON remains the source of truth; the boundary principle is unchanged: the SQLite index, like any future hosted backend, must connect through store interfaces — Decision, UI, Evaluation, and other layers must never depend on a concrete storage implementation.

## Snapshot and Replay Are Inputs

Comparability is not a report-stage decoration; it is part of the input contract.

- A branch / tag must be resolved to a commit hash when the run starts.
- Observation metadata such as timestamps and temporary workspace paths must not enter the replay digest.
- Dirty state, config hash, task revision, and configuration digests must be traceable.
- SnapshotGateResult must be persisted, and the Decision layer must consume it.
- When a key snapshot is missing, only weak / inconclusive / not_comparable conclusions may be produced.

## Evidence Is Structured

An artifact is factual material; an EvidenceItem is citable evidence. The two must not be conflated.

- stdout, stderr, diffs, and file outputs are ArtifactRefs.
- validation, scores, annotations, and snapshot gates are EvidenceItems.
- An EvaluationResult references evidence ids.
- A DecisionReport references evaluation ids and evidence ids.
- An evidence summary is a summary, not the full artifact.

When the original text must be shown, follow the EvidenceItem to its ArtifactRef and let the artifact viewer present it.

## Migration Is Explicit

Legacy v0.1.0 code may stay compatible, but the legacy model must not keep growing.

- New code uses canonical terminology first: Task, Configuration, RunCell, EvidenceItem, DecisionStatus.
- Legacy fields are handled only in adapters / loaders / migration bridges.
- Compatibility logic has tests whose names state "legacy".
- Migration proceeds by the MVP profile's P0-a / P0-b / P1 phases; no big-bang rewrites.
