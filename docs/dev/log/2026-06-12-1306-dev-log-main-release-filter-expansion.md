---
title: Development Log - Main Release Filter Expansion
doc_type: dev_log
status: active
created_at: 2026-06-12T13:06+08:00
updated_at: 2026-06-12T13:06+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - release
  - main-filter
related:
  - AGENTS.md
  - .codex/skills/micro-eval-release/SKILL.md
  - .codex/skills/micro-eval-release/scripts/release-to-main.sh
  - docs/engineering/release-process.md
  - docs/engineering/security-service-guidelines.md
---

# Development Log - Main Release Filter Expansion

## Summary

Expanded the dev-to-main release projection filter so public `main` excludes `.codex/`, `.understand-anything/`, and `docs/dev/` in addition to the existing dev-only specs, archives, references, bug reports, BRD, and PRD.

## Context

A workspace audit found three paths that should not be published to public `main`:

- `.understand-anything/` local analysis artifacts;
- `docs/dev/` development logs and decisions;
- `.codex/` Codex skills, release scripts, and local automation assets.

## Changes

- Updated `.codex/skills/micro-eval-release/scripts/release-to-main.sh` exclusion arrays and release-tree validation.
- Updated `AGENTS.md`, release skill validation instructions, release-process guidance, service security guidance, and generated main `AGENTS.md` template.
- Added `.understand-anything/` to `.gitignore` so local analysis output no longer appears as an untracked release blocker.

## Verification

- `bash -n .codex/skills/micro-eval-release/scripts/release-to-main.sh` — pass.
- `bash -n scripts/release-to-main.sh` — pass.
- `git check-ignore -v .understand-anything .understand-anything/config.json` confirms `.understand-anything/` is ignored.
- New main-exclusion grep correctly identifies current historical `main` `.codex/` and `docs/dev/` content as items that the next publish projection must remove.

## Risks and follow-ups

- The next actual publish should be run from a clean `dev` tree with `scripts/release-to-main.sh dev main`; it will remove historical `.codex/` and `docs/dev/` from `main`.
- Public `docs/README.md` may still mention directories that are intentionally absent from `main`; consider a future publish-docs projection if public docs navigation needs to be fully main-specific.
