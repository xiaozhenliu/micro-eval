---
title: Docs Directory Guide
doc_type: reference
status: active
created_at: 2026-06-03T08:35+08:00
updated_at: 2026-06-03T20:00+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - documentation
  - index
related:
  - docs/documentation-standard.md
  - docs/DEVELOPMENT.md
---

# Docs Directory Guide

This directory contains project documentation for `micro-eval`.
Use this README as the entry point for deciding where a document belongs.

## Documentation standard

- `documentation-standard.md` defines metadata, timestamp, naming, and placement rules for project documents.
- New documents should include YAML front matter and use minute-precision timestamps.
- If a historical document only has a date, treat the unknown time as `18:00` on that date.

## Directory map

| Path | Purpose |
| --- | --- |
| `DEVELOPMENT.md` | Engineering entry guide for local setup, common commands, verification, module map, and release readiness. |
| `documentation-standard.md` | Project-wide documentation standard and metadata format. |
| `analysis/` | Research, comparisons, investigations, trade-off analysis, and non-authoritative exploration notes. |
| `bug_reports/` | Review findings, defect inventories, and tracked remediation/tech-debt todo lists derived from code reviews. |
| `dev/` | Development-time records such as logs, decisions, implementation notes, and future engineering journals. |
| `dev/log/` | Chronological development logs. File names in this folder must include `dev-log`. |
| `engineering/` | Engineering guardrails for architecture, implementation, Python, frontend, testing, UX, security, and release process. |
| `references/` | External reference material and source notes. Large binary references should stay scoped and intentional. |
| `releases/` | Release readiness evidence, verification records, and release-specific quality gates. |
| `superpowers/specs/` | Authoritative long-term architecture, MVP scope, and test architecture specs. |
| `_archive/` | Superseded historical documents kept for traceability. |

## Key documents

| Document | Purpose |
| --- | --- |
| `_archive/invocation-evidence.md` | Archived historical notes related to legacy invocation evidence behavior. |
| `releases/2026-06-02-mvp-release-evidence.md` | MVP release-readiness evidence and verification summary. |
| `.codex/skills/micro-eval-release/SKILL.md` | Project-level executable release skill for versioning, release evidence, dependency inventory, dev commits, tags, and dev-to-main publishing. |
| `engineering/release-process.md` | Human-readable release reference that points back to the release skill. |

## Source-of-truth hierarchy

When documents conflict, prefer the narrower or more authoritative source in this order:

1. `docs/superpowers/specs/2026-06-02-unicorn-design.md` for long-term architecture boundaries.
2. `docs/superpowers/specs/2026-06-02-mvp-profile.md` for current MVP scope.
3. `docs/superpowers/specs/2026-06-02-test-architecture.md` for test architecture.
4. `docs/engineering/*.md` for implementation guardrails within their stated scope.
5. `docs/dev/**` for chronological notes and decisions that have not superseded an authoritative spec.
6. `docs/analysis/**` for exploratory or supporting analysis.

If a lower-level note needs to change an authoritative source, update the authoritative document first, then update dependent guidance.

## Adding a new document

1. Choose the correct directory from the map above.
2. Add YAML front matter following `docs/documentation-standard.md`.
3. Use minute-precision timestamps with timezone.
4. Link related source-of-truth documents instead of duplicating them.
5. Update this README if the document introduces a new area or changes how the docs are navigated.
