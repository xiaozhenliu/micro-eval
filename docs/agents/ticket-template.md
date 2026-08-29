---
title: Local Ticket Template
doc_type: reference
status: active
created_at: 2026-08-29T17:06+08:00
updated_at: 2026-08-29T17:06+08:00
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

File path: `.scratch/<effort>/issues/NN-lowercase-kebab.md`.

```md
---
id: LOCAL-EFFORT-01
title: Short title
effort: effort
type: task
status: ready
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T17:06+08:00
updated_at: 2026-08-29T17:06+08:00
---

# LOCAL-EFFORT-01 — Short title

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
- `effort` must be exactly the `.scratch/<effort>/` directory name; it is not
  always the `<EFFORT>` segment of the ID (`next-release` holds `LOCAL-NEXT-NN`).
- Timestamps are ISO-8601 with minute precision and an offset, no seconds.
- `blocked_by` is `[]` or a list of `LOCAL-...` / `GH-...` identifiers.
- Only `tags` and `related` may be added; any other key fails the check.
- Metadata belongs in front matter only. A `Key: value` line in the body is
  rejected as legacy metadata.

## Before resolving

Add `## Completion evidence` with the commit, dev log, changelog entry, or
verification command that proves delivery, set `status: resolved`, refresh
`updated_at`, and remove the pointer from `TODOS.md`.
