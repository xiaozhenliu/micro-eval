---
title: Work Tracking and Issue Governance
doc_type: reference
status: active
created_at: 2026-08-29T12:39+08:00
updated_at: 2026-09-05T13:20+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - work-register
  - ticket
  - governance
related:
  - docs/agents/triage-labels.md
  - docs/documentation-standard.md
  - docs/DEVELOPMENT.md
---

# Work Tracking and Issue Governance

This document defines the work-tracking contract. Since 2026-09-05 the
**Linear project `micro-eval` (team `GRO`) is the only Work Register**.
The former `TODOS.md` register and the `.scratch/<effort>/issues/`
front-matter ticket contract were retired by GRO-284; the old local
tickets remain under `.scratch/` as a read-only historical archive.

## Four objects, four responsibilities

| Object | Only responsibility | Canonical source |
| --- | --- | --- |
| Linear issue | Own the scope, acceptance criteria, dependencies, lifecycle, discussion, and completion evidence for all committed and roadmap work. | Linear, project `micro-eval`, team `GRO` |
| Roadmap item | Hold a short, not-yet-committed option and its entry trigger. | A `Backlog` Linear issue whose description keeps `Trigger / promote when` |
| Archived local ticket | Preserve the pre-migration record (scope, decisions, evidence). | Read-only Markdown under `.scratch/<effort>/issues/resolved/` |
| Completion evidence | Prove what was delivered and where it can be audited. | The Linear issue's `## Completion evidence`, plus `CHANGELOG.md` or a development log |

Linear is the index and the specification at the same time: an issue's
description holds its scope and acceptance criteria, and discussion
happens in its comments. There is no repo-side mirror of open work.

## Identifiers

- Linear issues use `GRO-<number>`, for example `GRO-285`.
- GitHub Issues keep `GH-<number>` and remain reserved for work that
  genuinely needs public feedback or collaboration.
- Historical local ticket IDs (`LOCAL-<WORKSTREAM>-<NN>`) are frozen;
  they identify archive files only and must never be reused.

## Workflow states and lanes

`Backlog`, `Todo`, `ready-for-agent`, `ready-for-human`,
`In Progress`, `Done`, and `Canceled` are the Linear workflow states of
team `GRO`; their meanings and the mapping from the retired local
vocabularies are defined in `triage-labels.md`. Planning position is
expressed by state, priority, and project assignment, not by repo files:

- `Backlog` — a roadmap option that is not yet committed; its
  description must keep the remaining scope and a `Trigger / promote
  when` condition.
- `Todo` — committed, not yet routed to an executor.
- `ready-for-agent` / `ready-for-human` — committed and routed.
- `In Progress` — being executed.
- `Done` — acceptance criteria and completion evidence are satisfied.
- `Canceled` — evaluated and will not be actioned (the old `wontfix`).
- Blocked work stays in its current state and records the dependency
  with Linear's blocked-by relation; `blocked` is not a workflow state.

## Issue-first threshold and flow

Create a Linear issue before implementing any behavior, schema,
security, release, or multi-file change. Also use an issue for work that
needs acceptance criteria, coordination, a dependency, or more than a
small focused edit. A one-file typo, formatting-only change, or
similarly trivial documentation correction may proceed without an
issue; when uncertain, create the issue first.

The normal flow is:

1. Capture an uncommitted idea as a `Backlog` issue with a trigger
   condition, or briefly in a dev log.
2. When work is committed, write the scope and acceptance criteria into
   one issue in project `micro-eval`; use `GH-<number>` only when
   public collaboration is genuinely needed.
3. Route execution by moving the issue to `ready-for-agent` or
   `ready-for-human`, and set priority independently of state.
4. Record blocking dependencies with Linear blocked-by relations.
5. Before implementation starts, split the issue into **sub-issues**:
   one sub-issue per independently deliverable, verifiable
   implementation step. The parent issue keeps the goal and the
   acceptance criteria; each sub-issue carries one step, its own
   checklist, and its own completion evidence. An issue that is small
   enough to be a single verifiable step does not need sub-issues.
6. When delivery is verified, move the issue to `Done` and record
   completion evidence in it; move user-visible facts to
   `CHANGELOG.md` or implementation evidence to a development log.

GitHub open/closed state is checked by a human during triage. Ordinary
CI does not require network access to Linear and does not mutate it.

## Labels and grouping

The workspace label group `area/*` replaces the retired workstream
directories (`landing-page`, `agent-collaboration`, `work-governance`,
`testing`, `engine`, `cost`, `schema`, `ui`, `adoption`, `platform`).
Tag every new issue with one `area/*` label; add `security`, `Feature`,
`Bug`, `Improvement`, or `UX` when they apply.

## Archived local tickets

`.scratch/<effort>/issues/resolved/` holds the pre-2026-09-05 ticket
archive. It is a historical record: it never receives new tickets, its
front matter stays frozen, and no active work may point at it. It stays
tracked on `dev` and classified private by the public projection.
`scripts/check-work-governance.py` validates the archive's structural
integrity and its private projection classification offline.

## Branch and visibility boundary

Work tracking and source changes happen on `dev`. `main` is a verified
public projection and is not a source-development branch. Public
documentation may describe this contract, but it must not link to
development-only Linear-external work records, `.scratch/`, or dev-log
paths that are absent from the public projection.

When the private development Pull Request workflow is active, its flow
is `work discovery → authorization / issue → lease → worktree → Pull
Request`. A Linear issue remains the authority for committed work; a
lease is only short-lived operational state and must never be mirrored
into repo files or issue metadata managed by the repo.
