---
title: Triage Roles and Issue Fields
doc_type: reference
status: active
created_at: 2026-08-29T12:39+08:00
updated_at: 2026-09-05T13:20+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - triage
  - ticket
  - lifecycle
related:
  - docs/agents/issue-tracker.md
---

# Triage Roles and Issue Fields

Since 2026-09-05 work is tracked in Linear (team `GRO`, project
`micro-eval`) and the workflow states below replace the retired local
`triage` / `executor` / `status` front-matter fields. This page records
the mapping so old archive tickets and dev logs stay readable.

## Workflow states

| Linear state | Meaning |
| --- | --- |
| `Backlog` | Roadmap option, not yet committed; description keeps the trigger condition. |
| `Todo` | Committed and ready, executor not yet routed (old `needs-triage`). |
| `ready-for-agent` | Scope and acceptance criteria are ready for an agent. |
| `ready-for-human` | A human must implement or decide the next step (old `ready-for-human` / `needs-info`). |
| `In Progress` | Work is currently being implemented (old `in_progress`). |
| `Done` | Acceptance criteria and completion evidence are satisfied (old `resolved`). |
| `Canceled` | Evaluated and will not be actioned (old `wontfix` / `archived`). |

Blocked work keeps its current state and records the dependency with
Linear's blocked-by relation; there is no blocked state.

## Executor routing

The retired `executor` field (`agent`, `human`, `pair`, `unassigned`)
maps to state plus assignee: `ready-for-agent`/`ready-for-human`
express the routing decision, and the Linear assignee names who is
expected to do the work. Routing may change without changing lifecycle
state.

## Priority

Priority is a Linear field (`Urgent` / `High` / `Medium` / `Low`),
independent of state. For the 2026-07-07 security audit it mapped
finding severity; for roadmap items it records the current relative
importance and promotion ordering only.

## Sub-issues

Before implementation starts, a parent issue is split into sub-issues:
one per independently deliverable, verifiable step. Sub-issues inherit
the parent's `area/*` label and carry their own completion evidence.
