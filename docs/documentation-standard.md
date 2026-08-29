---
title: Documentation Standard
doc_type: reference
status: active
created_at: 2026-06-03T08:35+08:00
updated_at: 2026-08-29T18:09+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - documentation
  - standards
  - metadata
related:
  - docs/README.md
  - docs/DEVELOPMENT.md
  - docs/agents/issue-tracker.md
---

# Documentation Standard

This document defines the project-wide documentation conventions for `micro-eval`.
It applies to Markdown documents under this repository unless a narrower document explicitly overrides formatting for a generated artifact.

## Goals

- Make project documents easy to classify, search, and maintain.
- Preserve the difference between release notes, engineering guides, research analysis, development logs, and decisions.
- Require minute-precision timestamps so future audits can reconstruct document history more accurately than date-only records.
- Keep documentation lightweight enough for a small AI engineering team.

## Required metadata

Every new project document should start with YAML front matter:

```yaml
---
title: Human-readable title
doc_type: reference
status: draft
created_at: 2026-06-03T18:00+08:00
updated_at: 2026-06-03T18:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - example
related:
  - docs/README.md
---
```

### Metadata fields

| Field | Required | Format | Meaning |
| --- | --- | --- | --- |
| `title` | Yes | Short string | Human-readable document title. |
| `doc_type` | Yes | Enum | One of `tutorial`, `how_to`, `reference`, `explanation`, `analysis`, `decision`, `dev_log`, `release_evidence`, `archive`, `external_reference`, `spec`. |
| `status` | Yes | Enum | One of `draft`, `active`, `superseded`, `archived`. |
| `created_at` | Yes | ISO-8601 minute precision | Creation timestamp, e.g. `2026-06-03T18:00+08:00`. |
| `updated_at` | Yes | ISO-8601 minute precision | Last meaningful content update timestamp. |
| `owner` | Yes | Short string | Person, team, or role responsible for upkeep. |
| `source_of_truth` | Yes | Boolean | `true` only when this document is authoritative for its scope. |
| `tags` | Recommended | String list | Search and grouping keywords. |
| `related` | Recommended | Path or URL list | Closely related documents, specs, issues, or evidence. |

## Timestamp rules

- Use ISO-8601 timestamps with minute precision and timezone: `YYYY-MM-DDTHH:MM+08:00`.
- Do not include seconds unless an external system requires them.
- For new documents, use the actual local creation/update minute.
- For historical documents that only have a date, set the unknown time to `18:00` on that known date.
  - Example: a historical document dated `2026-06-02` becomes `2026-06-02T18:00+08:00`.
- If both the historical date and time are unknown, use the migration date at `18:00`.
  - For this documentation-standard migration, that fallback is `2026-06-03T18:00+08:00`.
- When updating old documents, do not invent an exact original time; preserve uncertainty by applying the `18:00` default.

## File naming

Use lowercase kebab-case file names.

Recommended patterns:

```text
docs/<topic>.md
docs/analysis/YYYY-MM-DD-topic.md
docs/dev/log/YYYY-MM-DD-HHMM-dev-log-topic.md
docs/dev/decisions/YYYY-MM-DD-HHMM-decision-topic.md
docs/release-evidence-YYYY-MM-DD-topic.md
```

Rules:

- A timestamp in a file name means the document topic/event time, not the last update time; later edits only update `updated_at`.
- Development log file names must contain `dev-log`.
- Decision files under `docs/dev/` should contain `decision` in the file name.
- Historical or archived documents may keep existing names, but new files should follow the patterns above.
- Avoid spaces, uppercase words, and ambiguous abbreviations.

## Document type guidance

| `doc_type` | Use for | Typical location |
| --- | --- | --- |
| `tutorial` | Guided learning path for a newcomer. | `docs/` or feature-specific folder |
| `how_to` | Task-oriented operational instructions. | `docs/` |
| `reference` | Stable rules, APIs, contracts, or standards. | `docs/`, `docs/engineering/` |
| `explanation` | Conceptual background and rationale. | `docs/` |
| `analysis` | Research, comparison, investigation, or trade-off notes. | `docs/analysis/` |
| `decision` | Development or architecture decision records. | `docs/dev/decisions/` |
| `dev_log` | Chronological implementation progress, verification, and follow-ups. | `docs/dev/log/` |
| `release_evidence` | Release readiness and verification evidence. | `docs/releases/` |
| `archive` | Superseded historical material. | `docs/_archive/` |
| `external_reference` | Notes about external references and third-party material. | `docs/references/` |
| `spec` | Authoritative product, architecture, or test scope specs. | `docs/superpowers/specs/` |

## Development log format

Development logs should be concise and evidence-oriented:

```md
---
title: Development Log - Topic
doc_type: dev_log
status: active
created_at: 2026-06-03T18:00+08:00
updated_at: 2026-06-03T18:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
related:
  - docs/README.md
---

# Development Log - Topic

## Summary

## Context

## Changes

## Decisions

## Verification

## Risks and follow-ups
```

## Decision note format

Development decisions may live under `docs/dev/decisions/` and should record:

- Decision
- Context
- Options considered
- Rationale
- Consequences
- Review date, if applicable

Use `doc_type: decision` for these files.

## Maintenance rules

- Keep `docs/README.md` updated when adding or moving a documentation area.
- Prefer linking to source-of-truth documents instead of copying their content.
- Do not use documentation to redefine schema fields, module contracts, or MVP scope if an authoritative spec already exists.
- For release claims, include verification evidence or link to a release evidence document.
- For docs that mention subprocess, environment variables, artifacts, or workspace boundaries, link to `docs/engineering/security-guidelines.md` when relevant.

## Work records and tickets

The generic documentation metadata above applies to documents under `docs/`.
Development-only work records use the ticket contract in
`docs/agents/issue-tracker.md` instead of pretending that a ticket is a public
documentation page.

- `TODOS.md` is the single Work Register for unfinished work on `dev`; it is
  not a completion archive or a detailed specification.
- A local ticket carries its own YAML front matter — a stable
  `LOCAL-<WORKSTREAM>-<NN>` `id`, separate `status`, `triage`, and `executor`
  fields, and `created_at` / `updated_at` under the same timestamp rules as
  above — plus a `## Completion evidence` section when it reaches `resolved`
  or `archived`. The exact field list is defined in
  `docs/agents/issue-tracker.md`.
- A GitHub reference uses `GH-<number>` and leaves the Issue body as the sole
  public detail source.
- Completed work leaves the Work Register and is recorded in `CHANGELOG.md`, a
  development log, and/or the ticket's completion evidence as appropriate.
- Public documentation must not link to development-only `TODOS.md`,
  `.scratch/`, ticket, or log paths that the public projection intentionally
  omits.
