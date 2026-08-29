---
title: Development Documentation
doc_type: reference
status: active
created_at: 2026-06-03T08:35+08:00
updated_at: 2026-08-29T12:39+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - development
  - documentation
related:
  - docs/README.md
  - docs/documentation-standard.md
  - docs/agents/issue-tracker.md
---

# Development Documentation

This directory stores development-time records that are useful for maintainers but are not necessarily release notes or public-facing product documentation.

## Work records

`TODOS.md` is the only Work Register on `dev`. Durable local tickets, specs,
maps, and necessary attachments live in `.scratch/` and follow
`docs/agents/issue-tracker.md`; they are tracked on `dev` and excluded from the
public projection. This directory does not become a second backlog.

## Subdirectories

| Path | Purpose |
| --- | --- |
| `log/` | Chronological development logs. Every log file name must include `dev-log`. |
| `decisions/` | Development decision records. Decision file names should include `decision`. |

## How to use this area

- Use `log/` for what changed, why, verification performed, completion facts,
  and follow-ups.
- Use `decisions/` for durable choices that should be reviewed independently from daily progress.
- Keep release-facing summaries in `CHANGELOG.md`; do not turn development logs into release notes.
- When a ticket is resolved, keep its concise completion evidence, remove it
  from the Work Register, and retain the detailed implementation evidence here
  when future maintainers may need it.
