---
title: Work Tracking and Local Ticket Governance
doc_type: reference
status: active
created_at: 2026-08-29T12:39+08:00
updated_at: 2026-08-29T12:39+08:00
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

# Work Tracking and Local Ticket Governance

This document defines the work-tracking contract. `TODOS.md` on `dev` is the
only Work Register, and `.scratch/` is the durable private work-record
directory. This public guide describes the contract, while those development-
only records remain outside the public projection.

## Five objects, five responsibilities

| Object | Only responsibility | Canonical source |
| --- | --- | --- |
| Work Register | List every unfinished effort, its portfolio lane, and one navigable authority pointer. | `TODOS.md` on `dev` |
| Roadmap item | Hold a short, not-yet-committed option and its entry trigger. | `TODOS.md`, `Roadmap` lane |
| Local ticket | Own the scope, acceptance criteria, dependencies, lifecycle, discussion, and completion evidence for internal work. | A tracked Markdown file under the private work-record directory |
| GitHub Issue | Own the scope and public discussion for work that needs public feedback or collaboration. | The GitHub Issue body and discussion |
| Completion evidence | Prove what was delivered and where it can be audited; never re-open a completed backlog item. | Ticket evidence plus `CHANGELOG.md` or a development log |

The Work Register is an index, not a second specification. An active ticket or
Issue appears there once, with a short label and exactly one authority pointer.
Details belong only to that ticket or Issue.

## Stable identifiers and lanes

Use uppercase, stable source identifiers:

- Local tickets use `LOCAL-<EFFORT>-<NN>`, for example `LOCAL-NEXT-01`.
- GitHub Issues use `GH-<number>`, for example `GH-15`.
- A bare GitHub number and a priority-like label such as `[P8]` are not source
  identifiers. Priority is represented by lane and ordering, not by a second
  numbering system.

The Work Register has five portfolio lanes. Lanes describe planning, not
execution state:

- `Now` — committed work being executed immediately.
- `Next` — specified work queued for execution.
- `Waiting` — committed work waiting on an external dependency or decision.
- `Roadmap` — future options that are not yet committed and are not blocked
  tickets; every item records `Planning state: Roadmap (not blocked)` and a
  `Trigger / promote when:` condition.
- `Inbox` — untriaged ideas or requests; keep the description short until a
  decision is made.

`Now`, `Next`, and committed `Waiting` entries must each contain exactly one
`LOCAL-...` or `GH-...` pointer. `Roadmap` and `Inbox` may contain a brief
inline description and do not need a ticket before commitment. A Roadmap item
must retain its remaining scope and the condition that promotes it into a
ticket and an execution lane; it must not silently become a blocked item.

## Local ticket contract

Every file under `.scratch/<effort>/issues/` follows the path
`NN-lowercase-kebab.md` and starts with these fields:

```md
# LOCAL-EXAMPLE-01 — Short title

ID: LOCAL-EXAMPLE-01
Type: task
Status: ready
Triage: ready-for-agent
Executor: agent
Blocked by: None
```

`Type` is `task`, `research`, `prototype`, `grilling`, or `governance`. `Status` is the
lifecycle field and is one of `inbox`, `ready`, `in_progress`, `blocked`,
`resolved`, or `archived`. `resolved` is the single completion status;
`completed` is not used. `Triage` is an intake/routing role, and `Executor`
identifies who is expected to do the work. Their vocabularies are defined
separately in `triage-labels.md` and must not be merged into `Status`.

`Blocked by:` is `None` or a comma-separated list of stable `LOCAL-...` or
`GH-...` identifiers. A blocked committed ticket uses `Status: blocked` and
belongs in `Waiting`. An optional future dependency belongs in `Roadmap`
until its trigger occurs.

The body contains `What to build`, acceptance criteria, and relevant context.
Terminal tickets contain a `## Completion evidence` section with the commit,
development log, changelog, release evidence, or verification command that
proves delivery. Conversation history, if needed, is appended under
`## Comments`. The ticket may remain as a durable record after it leaves the
Work Register.

`.scratch/` is tracked on `dev`. Its allowed content is limited to tickets,
`spec.md`, `map.md`, and necessary attachments. Caches, build products, runtime
data, logs, databases, credentials, and secret-bearing files do not belong
there. The release projection policy classifies `.scratch/**` as private and
forbids it in public output.

## Ticket-first threshold and flow

Create the ticket and add its one pointer to `TODOS.md` before implementing
any behavior, schema, security, release, or multi-file change. Also use a
ticket for work that needs acceptance criteria, coordination, a dependency,
or more than a small focused edit. A one-file typo, formatting-only change,
or similarly trivial documentation correction may proceed without a ticket;
when uncertain, use the ticket-first path.

The normal flow is:

1. Capture an uncommitted idea in `Inbox` or a future option in `Roadmap`.
2. When work is committed, create one local ticket by default, or use one
   GitHub Issue when public collaboration is genuinely needed. Add exactly one
   pointer to `Now`, `Next`, or `Waiting` before implementation starts.
3. Set the ticket's triage role and executor independently from its lifecycle
   status. Move the portfolio lane as planning changes.
4. Record a blocking dependency in `Blocked by:` and use `Waiting` for
   committed blocked work. Do not use `Blocked` as a synonym for Roadmap.
5. When delivery is verified, set `Status: resolved`, record completion
   evidence, remove the pointer from `TODOS.md`, and move user-visible facts to
   `CHANGELOG.md` or implementation evidence to a development log.
6. Keep the resolved ticket for auditability; archive it only when its record
   is intentionally retired.

GitHub open/closed state is checked by a human during triage. Ordinary CI and
the local governance check do not require network access or mutate GitHub.

## Branch and visibility boundary

Work tracking and source changes happen on `dev`. `main` is a verified public
projection and is not a source-development branch. Public documentation may
describe this contract, but it must not link to development-only Work Register,
ticket, or log paths that are absent from the public projection.
