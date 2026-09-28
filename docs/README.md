---
title: Docs Directory Guide
doc_type: reference
status: active
created_at: 2026-06-03T08:35+08:00
updated_at: 2026-09-27T15:58+08:00
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

## Bilingual engineering docs

`docs/engineering/**` and `DEVELOPMENT.md` are bilingual. The English file at the
plain name is authoritative; the `*.zh-CN.md` companion is a translation for
human reading only, marked `agent_read: false` in its front matter with an
`authoritative:` pointer to the English file. Agents and automation must read
the English version; when the two disagree, the English version wins.

## Directory map

| Path | Purpose |
| --- | --- |
| `DEVELOPMENT.md` | Engineering entry guide for local setup, common commands, verification, module map, and release readiness. |
| `documentation-standard.md` | Project-wide documentation standard and metadata format. |
| `analysis/` | Research, comparisons, investigations, trade-off analysis, and non-authoritative exploration notes. |
| `bug_reports/` | Review findings, defect inventories, and tracked remediation/tech-debt todo lists derived from code reviews. |
| `agents/` | Public agent-facing contracts, including work tracking and triage vocabulary. |
| `dev/` | Development-time records such as logs, decisions, implementation notes, and future engineering journals. |
| `dev/plans/` | Detailed implementation plans referenced by Linear issues; scope, acceptance criteria, and execution status remain in Linear. |
| `dev/log/` | Chronological development logs. File names in this folder must include `dev-log`. |
| `dev/decisions/` | Development decisions and lightweight design records. File names in this folder should include `decision`. |
| `engineering/` | Engineering guardrails for architecture, implementation, Python, frontend, testing, UX, security, and release process. |
| `references/` | External reference material and source notes. Large binary references should stay scoped and intentional. |
| `releases/` | Release readiness evidence, verification records, and release-specific quality gates. |
| `superpowers/specs/` | Authoritative long-term architecture, current-state, Team Server, and test architecture specs. Only documents that describe what is true now live here. |
| `_archive/` | Superseded historical documents kept for traceability. |
| `_archive/plans/` | Delivered one-off implementation plans (June–July 2026). New detailed implementation plans belong under `dev/plans/` and are referenced by Linear issues; do not add plans to this archive, the read-only `.scratch/` archive, or `superpowers/`. |

## Key documents

| Document | Purpose |
| --- | --- |
| `_archive/invocation-evidence.md` | Archived historical notes related to legacy invocation evidence behavior. |
| `agents/issue-tracker.md` | Linear work-tracking contract: Work Register, issue states, sub-issues, and completion evidence. |
| `agents/triage-labels.md` | Linear workflow-state vocabulary and the mapping from the retired local fields. |
| `releases/2026-06-02-mvp-release-evidence.md` | MVP release-readiness evidence and verification summary. |
| `releases/2026-06-12-v0.2.0-release-evidence.md` | Phase 2 / v0.2.0 release-readiness evidence and verification summary. |
| `releases/2026-06-12-v0.2.0-dependency-inventory.md` | Dependency inventory for v0.2.0 release preparation. |
| `engineering/release-process.md` | Human-readable release reference for the repository release scripts and projection gates. |

For the most accurate and up-to-date version record, see the root [`CHANGELOG.md`](../CHANGELOG.md) — dedicated release evidence documents have not been produced for every release since v0.3.0.

## Work governance

On `dev`, the Linear project `micro-eval` (team `GRO`) is the only Work
Register since 2026-09-05, and `.scratch/` contains the read-only archive of
the retired local tickets plus their maps and attachments. The public contract
is `agents/issue-tracker.md`; the public projection omits `.scratch/` and the
development log directory. Do not add links from public docs to those omitted
records.

## Source-of-truth hierarchy

When documents conflict, prefer the narrower or more authoritative source in this order:

1. `docs/superpowers/specs/2026-06-02-unicorn-design.md` for long-term architecture boundaries.
2. `docs/superpowers/specs/2026-06-02-unicorn-design.md` §9–§10 for the current implemented scope (the historical MVP Profile is archived at `docs/_archive/2026-06-02-mvp-profile.md`).
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
