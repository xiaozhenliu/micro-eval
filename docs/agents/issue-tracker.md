---
title: Work Tracking and Local Ticket Governance
doc_type: reference
status: active
created_at: 2026-08-29T12:39+08:00
updated_at: 2026-08-29T16:52+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - work-register
  - ticket
  - governance
related:
  - docs/agents/ticket-template.md
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
`NN-lowercase-kebab.md`. Ticket metadata lives in YAML front matter at the very
top of the file, in the same style as `docs/documentation-standard.md`. Prose
never carries metadata: a `Key: value` line in the body is ordinary text, not a
field.

This document is the contract. To write an ordinary ticket, copy
`docs/agents/ticket-template.md` instead of reading this section.

```md
---
id: LOCAL-EXAMPLE-01
title: Short title
effort: example
type: task
status: ready
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T16:52+08:00
updated_at: 2026-08-29T16:52+08:00
tags:
  - example
related:
  - docs/agents/issue-tracker.md
---

# LOCAL-EXAMPLE-01 — Short title

## What to build

...

## Acceptance criteria

- ...
```

### Front matter fields

| Field | Required | Format | Meaning |
| --- | --- | --- | --- |
| `id` | Yes | `LOCAL-<EFFORT>-<NN>` | Stable ticket identifier; unique across active and archived tickets and never reused. |
| `title` | Yes | Short string | Ticket title; must match the text after `— ` in the H1 heading. |
| `effort` | Yes | Lowercase kebab-case | Effort this ticket belongs to; must equal the `.scratch/<effort>/` directory name. |
| `type` | Yes | Enum | One of `task`, `research`, `prototype`, `grilling`, `governance`. |
| `status` | Yes | Enum | Lifecycle status; see `triage-labels.md`. |
| `triage` | Yes | Enum | Intake/routing role; see `triage-labels.md`. |
| `executor` | Yes | Enum | Expected implementer; see `triage-labels.md`. |
| `blocked_by` | Yes | List of stable IDs | `[]` when nothing blocks it; otherwise `LOCAL-...` / `GH-...` entries. |
| `created_at` | Yes | ISO-8601 minute precision | Creation timestamp, e.g. `2026-08-29T16:52+08:00`. |
| `updated_at` | Yes | ISO-8601 minute precision | Last meaningful update timestamp. |
| `tags` | Optional | String list | Search and grouping keywords. |
| `related` | Optional | Path or URL list | Closely related documents, specs, Issues, or evidence. |

No other keys are allowed. Unknown keys fail the governance check rather than
being silently ignored, so the vocabulary cannot drift ticket by ticket.

`status` is the lifecycle field. `resolved` is the single completion status;
`completed`, `done`, and `in-progress` are not accepted spellings. `triage` is
an intake/routing role and `executor` identifies who is expected to do the
work; their vocabularies are defined in `triage-labels.md` and must not be
merged into `status`.

A blocked committed ticket uses `status: blocked`, lists its dependencies in
`blocked_by`, and belongs in `Waiting`. An optional future dependency belongs
in `Roadmap` until its trigger occurs.

Timestamps follow the project timestamp rule: ISO-8601 with minute precision
and a timezone offset, no seconds. For a historical ticket whose exact time is
unknown, use `18:00` on the known date.

### Body structure

The H1 heading is `# <id> — <title>`. The body then contains:

- `## What to build` — the scope, in user-visible terms.
- `## Acceptance criteria` — a checkable list.
- Optional sections such as `## Context`, `## Confirmed decisions`, or
  `## Comments` for discussion history.
- `## Completion evidence` — required once `status` is `resolved` or
  `archived`; records the commit, development log, changelog entry, release
  evidence, or verification command that proves delivery.

The ticket may remain as a durable record after it leaves the Work Register.

### Storage layout

Active tickets live directly under `.scratch/<effort>/issues/`. Once every
ticket in an effort is `resolved`, the resolved files are filed under
`.scratch/<effort>/issues/resolved/` so that `issues/` shows only unfinished
work. Archiving is a move with history preserved (`git mv`): the ticket keeps
its ID, `status: resolved`, and full completion evidence, remains the
authority for its record, and its ID stays reserved — archived IDs are still
checked for uniqueness and must never be reused.

`.scratch/` is tracked on `dev`. Its allowed content is limited to tickets,
`spec.md`, `map.md`, and necessary attachments. Caches, build products, runtime
data, logs, databases, credentials, and secret-bearing files do not belong
there. The release projection policy classifies `.scratch/**` as private and
forbids it in public output.

### Effort map files

An optional `.scratch/<effort>/map.md` groups an effort's tickets. It uses the
generic documentation front matter from `docs/documentation-standard.md`
(`title`, `doc_type: reference`, `status`, `created_at`, `updated_at`, `owner`,
`source_of_truth: false`), not the ticket front matter above. A map is a
navigation record, never a second Work Register.

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
3. Set the ticket's `triage` role and `executor` independently from its
   lifecycle `status`. Move the portfolio lane as planning changes.
4. Record a blocking dependency in `blocked_by` and use `Waiting` for
   committed blocked work. Do not use `Blocked` as a synonym for Roadmap.
5. When delivery is verified, set `status: resolved`, record completion
   evidence, remove the pointer from `TODOS.md`, and move user-visible facts to
   `CHANGELOG.md` or implementation evidence to a development log.
6. Keep the resolved ticket for auditability; when an effort's tickets are
   all resolved, file them under that effort's `issues/resolved/` directory.

GitHub open/closed state is checked by a human during triage. Ordinary CI and
the local governance check do not require network access or mutate GitHub.

## Branch and visibility boundary

Work tracking and source changes happen on `dev`. `main` is a verified public
projection and is not a source-development branch. Public documentation may
describe this contract, but it must not link to development-only Work Register,
ticket, or log paths that are absent from the public projection.
