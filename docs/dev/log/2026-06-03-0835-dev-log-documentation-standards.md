---
title: Development Log - Documentation Standards
doc_type: dev_log
status: active
created_at: 2026-06-03T08:35+08:00
updated_at: 2026-06-03T08:35+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - documentation
related:
  - docs/README.md
  - docs/documentation-standard.md
  - docs/dev/README.md
---

# Development Log - Documentation Standards

## Summary

Added a project-wide documentation standard, a `docs/` directory guide, and a dedicated `docs/dev/log/` area for development logs.

## Context

The project already had release notes, engineering guidance, analysis documents, and authoritative specs, but did not yet have a unified metadata convention or a dedicated development log location.

## Changes

- Added `docs/documentation-standard.md` with metadata, timestamp, naming, document type, development log, and decision note rules.
- Added `docs/README.md` to explain the purpose of each documentation area.
- Added `docs/dev/README.md` for development-time records.
- Added this initial development log under `docs/dev/log/` with `dev-log` in the file name.

## Decisions

- Use ISO-8601 timestamps with minute precision and timezone: `YYYY-MM-DDTHH:MM+08:00`.
- Default unknown historical times to `18:00` on the known date.
- Keep development logs separate from `CHANGELOG.md` so release notes remain user-facing and concise.
- Reserve `docs/dev/` for logs, future development decisions, and other maintainer-facing records.

## Verification

- Ran `git diff --check -- docs`; no whitespace errors were reported.
- Checked that every Markdown file under `docs/dev/log/` contains `dev-log` in its file name.

## Risks and follow-ups

- Existing historical documents do not yet all include YAML front matter.
- A future documentation migration can add metadata to older documents using the `18:00` fallback rule.
