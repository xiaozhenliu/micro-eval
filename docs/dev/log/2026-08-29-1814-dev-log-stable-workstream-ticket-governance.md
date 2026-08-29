---
title: Development Log - Stable Workstream Ticket Governance
doc_type: dev_log
status: active
created_at: 2026-08-29T18:14+08:00
updated_at: 2026-08-29T18:14+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - work-governance
related:
  - docs/agents/issue-tracker.md
  - .scratch/work-governance/issues/resolved/05-organize-tickets-by-stable-workstream.md
---

# Development Log - Stable Workstream Ticket Governance

## Summary

Changed local ticket routing from an unconstrained per-effort directory match
to stable workstreams with authoritative scope maps. Portfolio timing remains
in `TODOS.md`; workstream names now describe durable ownership domains.

## Context

The completed release-hardening tickets lived under `next-release`. A new
Decision Layer ticket was appended there because the checker verified only
directory/frontmatter equality and maps were optional, even though the new
work did not belong to the historical release initiative.

## Changes

- Required every `.scratch/<effort>/` workstream to have a `map.md` with
  `Scope`, `Boundaries`, and active/archived status.
- Added fail-closed checks for missing maps, vague active workstream names,
  active tickets under archived workstreams, and ticket ID/workstream drift.
- Added maps for monid and site-skill, strengthened the work-governance map,
  and archived the historical next-release map.
- Moved the comparative verdict ticket to
  `LOCAL-COMPARATIVE-DECISION-01` under its own workstream and updated active
  references.
- Synchronized the authoritative governance guide, ticket template,
  documentation standard, and generated/release AGENTS instruction pair.

## Decisions

- The existing `effort` frontmatter field is retained for compatibility but
  now means a stable workstream slug.
- A workstream map is authoritative only for routing scope and boundaries;
  `TODOS.md` remains the Work Register and each ticket owns its details.
- The archived `next-release` / `LOCAL-NEXT` naming remains readable as a
  historical compatibility exception and cannot receive active tickets.

## Verification

- `uv run pytest -q tests/unit/test_work_governance.py` — 15 passed.
- `uv run python scripts/check-work-governance.py` — passed.
- `git diff --check` — passed.

## Risks and follow-ups

- The vague-name check intentionally rejects a small explicit set rather than
  trying to classify arbitrary language. Scope-map review remains the primary
  routing decision.
- The repository environment does not currently provide `ruff`; no new lint
  dependency was introduced for this governance-only change.
