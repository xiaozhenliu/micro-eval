---
title: micro-eval Engineering Guidelines Index
language: en
authoritative: true
doc_type: reference
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-09-27T16:00+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - micro-eval
related:
  - docs/README.md
  - docs/documentation-standard.md
---

# micro-eval Engineering Guidelines Index

This document is the entry point for engineering guidelines. It routes; it does not redefine product goals, module contracts, field schemas, or MVP scope. Chinese companion translations (`*.zh-CN.md`) exist for human reading only — this English file set is authoritative, and agents must follow the English versions.

## Source of Truth

Never let one fact have multiple authoritative sources. Before implementing, decide which document to consult.

| Question | Authoritative source | May this directory redefine it |
|---|---|---|
| Why the product exists, which business problem it solves | `micro-eval-brd.md` | No |
| Long-term modules, architecture invariants, Stable IDs, evidence model | `docs/superpowers/specs/2026-06-02-unicorn-design.md` Part I | No |
| Which capabilities are enabled now, which are out of scope, migration phasing | `docs/superpowers/specs/2026-06-02-unicorn-design.md` §9–§10 (historical MVP profile: `docs/_archive/2026-06-02-mvp-profile.md`) | No |
| How micro-eval's own code is tested | `docs/superpowers/specs/2026-06-02-test-architecture.md` | No |
| How code is organized, implementation trade-offs, stack constraints | `docs/engineering/*` | Yes |

Conflict resolution:

1. The user's current explicit instruction wins.
2. Repository rules in `AGENTS.md` win over engineering guidelines.
3. Unicorn Part I wins over the MVP profile.
4. The MVP profile wins over implementation plans.
5. Engineering guidelines win over ad-hoc implementation preferences.

## Which file to read when

Do not read the whole `docs/engineering/` directory by default. Read a file only when the task hits one of these scenarios.

| Trigger | File to read |
|---|---|
| Architecture boundaries, module ownership, cross-module dependencies | `architecture-guardrails.md` |
| Implementation design, module interfaces, migration phasing, store/adapter/evidence landing | `implementation-principles.md` |
| Python CLI / engine / schema / subprocess | `python-guidelines.md` |
| Next.js / TypeScript / zod / API routes / UI data access | `frontend-guidelines.md` |
| Test plan, contract tests, flake control | `testing-guidelines.md` |
| ResultMatrix, Decision, Artifact/Evidence presentation | `ux-guidelines.md` |
| Work Register (Linear), issue states, triage and completion evidence | `../agents/issue-tracker.md`; `../agents/triage-labels.md` |
| Security index / unsure which security guideline applies | `security-guidelines.md` |
| Product/service security: CLI, local UI/API, reports, release packages, future service offering | `security-service-guidelines.md` |
| User run security: secrets, workspaces, network caveats, artifacts, evidence | `security-user-run-guidelines.md` |
| Development security: subprocess, env, redaction, workspace, artifact, decision safety | `security-development-guidelines.md` |
| Version numbers, CHANGELOG, release evidence, dependency inventory, release commits, tags, dev→main release | `release-process.md` and the release skill in the dev environment; the single copy of the scripts lives in `scripts/release/` |

## Implementation Plan Ready Gate

Before entering an implementation plan, the relevant spec / profile must be clear enough.

Work may enter an implementation plan if and only if:

- The owning Unicorn module is identified.
- The MVP / future boundary is identified.
- Inputs, outputs, and persistence locations are identified.
- Stable IDs and schema_version requirements for key objects are identified.
- Whether Pydantic / zod parity is affected is identified.
- Whether snapshot / replay identity is affected is identified.
- Whether artifacts / evidence are produced is identified.
- Error paths and caveats are identified.
- Security and redaction boundaries are identified.
- At least one executable acceptance test exists.
- No key semantics are deferred with "decide during implementation".

If the Ready Gate is not met, fix Unicorn / the MVP profile / the test architecture first instead of writing an implementation plan.

## Documentation Discipline

Doc updates follow the single-authority principle.

- Changing long-term architecture, invariants, module boundaries: change Unicorn Part I.
- Changing the current MVP scope or migration phasing: change the MVP profile.
- Changing test strategy: change the test architecture.
- Changing code organization, engineering principles, stack constraints, UX implementation constraints: change the matching file in this directory.
- Changing concrete implementation tasks: change the implementation plan.

Never redefine schemas inside an implementation plan, never copy field tables into the engineering guidelines, and never promise capabilities in a README that are not bound to the profile.
