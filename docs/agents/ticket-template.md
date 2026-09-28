---
title: Local Ticket Template
doc_type: reference
status: active
created_at: 2026-08-29T17:06+08:00
updated_at: 2026-08-29T18:09+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - ticket
  - template
related:
  - docs/agents/issue-tracker.md
  - docs/agents/triage-labels.md
---

# Local Ticket Template

Copy this when creating a local ticket. `docs/agents/issue-tracker.md` is the
authoritative contract; this page only exists so an ordinary ticket can be
written correctly without reading it.

File path: `.scratch/<effort>/issues/NN-lowercase-kebab.md`, where `<effort>`
is the stable workstream selected through its active `map.md`.

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
created_at: 2026-08-29T17:06+08:00
updated_at: 2026-08-29T17:06+08:00
---

# LOCAL-EXAMPLE-01 — Short title

## What to build

...

## Acceptance criteria

- ...
```

The values above are the ordinary defaults. For any other `type`, `status`,
`triage`, or `executor` value, use the vocabularies in
`docs/agents/triage-labels.md`.

## What is easy to get wrong

- `id`'s trailing number must equal the file's `NN` prefix.
- `title` must be exactly the text after the em dash in the H1.
- Choose an existing active workstream only when its map `Scope` and
  `Boundaries` fit. Otherwise create a descriptive workstream and map first;
  `TODOS.md` lanes express timing, so relative names such as `next-release`
  are not new-work destinations.
- `effort` must be exactly the `.scratch/<effort>/` directory name. New ticket
  IDs use the uppercase workstream slug; `next-release` / `LOCAL-NEXT-NN` is a
  historical compatibility exception.
- Timestamps are ISO-8601 with minute precision and an offset, no seconds.
- `blocked_by` is `[]` or a list of `LOCAL-...` / `GH-...` identifiers.
- Only `tags` and `related` may be added; any other key fails the check.
- Metadata belongs in front matter only. A `Key: value` line in the body is
  rejected as legacy metadata.

## Before resolving

Add `## Completion evidence` with the commit, dev log, changelog entry, or
verification command that proves delivery, set `status: resolved`, refresh
`updated_at`, remove the pointer from `TODOS.md`, and move the ticket into its
workstream's `issues/resolved/` directory.
