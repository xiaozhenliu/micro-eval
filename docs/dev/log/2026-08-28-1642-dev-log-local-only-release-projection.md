---
title: Development Log - Local-only Release Projection
doc_type: dev_log
status: superseded
created_at: 2026-08-28T16:42+08:00
updated_at: 2026-08-28T17:09+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - release
  - safety
related:
  - scripts/release-to-main.sh
  - docs/engineering/release-process.md
  - .codex/skills/micro-eval-release/SKILL.md
  - docs/dev/log/2026-08-28-1709-dev-log-fail-closed-public-release.md
---

# Development Log - Local-only Release Projection

## Summary

The formal `dev` → `main` release entry now defaults to local-only projection.
Updating `origin/main` requires an explicit `--push` selection and the script
announces the exact remote branch before executing the push.

## Context

The v0.4.5 release was authorized for local projection only, but the release
script unconditionally pushed `main`. The implementation needed an enforceable
remote-action boundary rather than relying on operator knowledge.

## Changes

- Added default `local-only` behavior plus explicit `--local-only` and
  `--no-push` spellings.
- Added explicit `--push` mode with a pre-push `origin/main` announcement.
- Added `--help`, strict mode-conflict handling, and fixed `dev`/`main` branch
  validation.
- Synchronized the release Skill, release process, generated `AGENTS.md`
  template, and changelog.
- Added isolated Git-repository regression coverage for local-only and push
  paths.

## Decisions

- `scripts/release-to-main.sh dev main` remains the compatibility entry and is
  safe by default.
- Remote publication stays in the same gated release workflow but is unreachable
  without an explicit `--push` argument.
- Push authorization covers only `origin/main`; it does not imply authorization
  to push `dev` or tags.

## Verification

- `uv run pytest -q tests/integration/test_release_to_main.py` — 6 passed.
- `scripts/release/preflight-release.sh 0.4.5` — passed: version consistency,
  compileall, 633 pytest tests, UI lint/build, sdist/wheel build, diff checks,
  and forbidden shell-subprocess scan.
- `bash -n scripts/release-to-main.sh` — passed.
- `cmp AGENTS.md .codex/skills/micro-eval-release/assets/templates/agents-publish-template.md`
  — passed.
- No project remote was pushed. The push regression test used only an isolated
  temporary bare Git repository.

Security boundaries were unchanged: the script passes fixed release branch
names to Git as quoted argv, does not add shell interpolation, does not handle
secrets, and does not touch evaluation workspaces or artifacts.

## Risks and follow-ups

- Superseded by the fail-closed public projection Module and separate
  verified-receipt push flow recorded in the related 17:09 development log.
