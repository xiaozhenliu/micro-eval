---
title: Development Log - Frontmatter Ticket Format
doc_type: dev_log
status: active
created_at: 2026-08-29T16:57+08:00
updated_at: 2026-08-29T16:57+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - governance
  - ticket
related:
  - docs/agents/issue-tracker.md
  - docs/agents/triage-labels.md
  - docs/documentation-standard.md
---

# Development Log - Frontmatter Ticket Format

## Summary

Local tickets now carry their metadata in YAML front matter instead of
plain-text field lines scattered through the body. The governance check parses
only that front matter and fails closed on missing, unknown, or malformed
fields. All existing work records were migrated.

## Context

The ticket contract only required a block of `ID:` / `Type:` / `Status:` lines
"at the start" of the file, and the checker collected fields by scanning every
line of the document with a permissive `Key: value` regex. Two consequences:

- Metadata drifted to different positions per ticket — some tickets put the
  block after a `**What to build:**` paragraph — so there was no predictable
  place to read a ticket's state.
- Any prose line shaped like `Key: value` could be silently reinterpreted as
  metadata, and there was no place to record creation/update times, unlike
  every document under `docs/`.

The drift was real, not theoretical: `.scratch/monid/issues/01-*.md` carried
`Status: in-progress` (the contract spells it `in_progress`), which is why the
governance check was failing before this change.

## Changes

- `docs/agents/issue-tracker.md` — replaced the plain-field contract with a
  ticket front matter specification: required `id`, `title`, `effort`, `type`,
  `status`, `triage`, `executor`, `blocked_by`, `created_at`, `updated_at`;
  optional `tags` and `related`; no other keys. Added body structure rules and
  a separate rule that effort `map.md` files use the generic documentation
  front matter.
- `docs/agents/triage-labels.md`, `docs/documentation-standard.md`,
  `AGENTS.md`, `TODOS.md`, and the release skill's AGENTS template now use the
  lowercase front matter key names.
- `scripts/check-work-governance.py` — replaced the whole-file `FIELD_RE` scan
  with a strict, dependency-free front matter parser (scalars, inline empty
  lists, block lists) plus `_check_ticket_frontmatter`. New failures: missing
  or unterminated front matter, unknown key, missing required key, scalar/list
  shape mismatch, invalid enum value, non ISO-8601 timestamp, `effort` that
  disagrees with the directory, `id` number that disagrees with the file
  number, H1 that disagrees with `id`/`title`, and legacy metadata lines left
  in the body. Archived tickets now go through the same full validation and
  must be in a terminal status.
- Migrated 16 tickets and 2 effort maps to the new format, and corrected
  `in-progress` to `in_progress`.

## Decisions

- Front matter uses lowercase snake_case keys to match
  `docs/documentation-standard.md`, so one convention covers both docs and
  work records.
- Unknown keys are rejected rather than ignored, so the vocabulary cannot
  drift ticket by ticket.
- The parser stays stdlib-only. The script is documented as runnable with a
  bare `python3`, so it must not depend on PyYAML being installed.
- `effort` is validated against the directory name, but the `<EFFORT>` segment
  of the ID is not: `next-release` legitimately holds `LOCAL-NEXT-NN`. The
  `NN` segment is validated against the file number instead.

## Verification

- `uv run python scripts/check-work-governance.py` — passed.
- `uv run pytest tests/unit/test_work_governance.py` — 10 passed, including 5
  new regressions (missing front matter, unknown key, legacy body metadata,
  effort mismatch, date-only timestamp).
- `uv run pytest tests/unit` — 542 passed.
- `site_update.py plan` — 0 behavior paths, 0 impact rules; no public site
  impact.
- `git diff --check` — clean.

## Security

- No subprocess, environment, artifact, or workspace surface changed. The
  script's existing `git` calls still pass argument lists, never a shell
  string.
- No secrets are read or emitted; the checker reports only repository-relative
  paths.
- The `.scratch/**` and `TODOS.md` private-projection assertions are unchanged
  and still pass, so work records remain excluded from public output.

## Risks and follow-ups

- The parser accepts only the YAML subset the contract uses. A ticket written
  with nested mappings or multi-line scalars fails the check rather than being
  parsed; that is intentional, but it means the spec and parser must be
  updated together if the format ever needs to grow.
