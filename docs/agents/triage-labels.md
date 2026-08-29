---
title: Triage Roles and Ticket Fields
doc_type: reference
status: active
created_at: 2026-08-29T12:39+08:00
updated_at: 2026-08-29T12:39+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - triage
  - ticket
  - lifecycle
related:
  - docs/agents/issue-tracker.md
---

# Triage Roles and Ticket Fields

Triage answers “what routing decision is needed?” It does not describe
execution progress. A local ticket therefore carries separate `Triage`,
`Executor`, and `Status` fields.

## Triage role

These values are intake and routing labels:

| Role | Meaning |
| --- | --- |
| `needs-triage` | Maintainer still needs to evaluate scope and priority. |
| `needs-info` | Work is waiting for information from the requester or reporter. |
| `ready-for-agent` | Scope and acceptance criteria are ready for an agent. |
| `ready-for-human` | A human must implement or decide the next step. |
| `wontfix` | The request has been evaluated and will not be actioned. |

## Executor

`Executor` identifies the expected implementer: `unassigned`, `agent`,
`human`, or `pair`. It may change without changing the lifecycle status.

## Lifecycle status

`Status` records the ticket lifecycle:

| Status | Meaning |
| --- | --- |
| `inbox` | Recorded but not yet ready for execution. |
| `ready` | Accepted with clear criteria and ready to start. |
| `in_progress` | Work is currently being implemented or investigated. |
| `blocked` | Committed work cannot proceed until `Blocked by:` is cleared. |
| `resolved` | Acceptance criteria and completion evidence are satisfied. |
| `archived` | A resolved record was intentionally retired from active history. |

Use `resolved` as the only normal completion spelling. Do not substitute
`completed`, `done`, or a triage label for lifecycle status.

## Portfolio lane mapping

`Now`, `Next`, `Waiting`, `Roadmap`, and `Inbox` are Work Register planning
lanes, not ticket statuses. A `blocked` committed ticket belongs in `Waiting`;
an uncommitted future option belongs in `Roadmap` and may have no ticket yet.
