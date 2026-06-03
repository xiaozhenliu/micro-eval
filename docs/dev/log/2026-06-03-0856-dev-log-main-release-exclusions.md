---
title: Development Log - Main Release Exclusions
doc_type: dev_log
status: active
created_at: 2026-06-03T08:56+08:00
updated_at: 2026-06-03T09:34+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - release
  - main
  - branch-policy
related:
  - AGENTS.md
  - scripts/release-to-main.sh
  - docs/documentation-standard.md
---

# Development Log - Main Release Exclusions

## Summary

Added a scripted release path so `main` can receive releasable content from `dev` while excluding dev-only docs and preserving generated main-branch agent guardrails.

## Changes

- Added `scripts/release-to-main.sh` and publish templates under `scripts/release/templates/`.
- Refactored `AGENTS.md` into stable boot rules, action-oriented source routing, release rules, documentation rules, and the restored OMX injected section.
- Split security guidance into a routing index plus three source-of-truth files: product/service safety, user run safety, and development implementation safety.

## Decisions

- Do not ask agents to manually merge or checkout `main` for release work.
- Keep `docs/superpowers/`, `docs/_archive/`, `docs/references/`, BRD, and PRD out of `main`.
- Generate main `AGENTS.md` / `CLAUDE.md` from explicit publish templates.

## Verification

- `bash -n scripts/release-to-main.sh`
- `git diff --check` on changed docs and scripts
- Confirmed all files under `docs/dev/log/` include `dev-log` in the file name

## Follow-up

Test the release script during the next actual release merge before pushing `main`.
