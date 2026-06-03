---
title: Development Log - Release Workflow
doc_type: dev_log
status: active
created_at: 2026-06-03T13:15+08:00
updated_at: 2026-06-03T13:40+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - release
related:
  - docs/engineering/release-process.md
  - .codex/skills/micro-eval-release/SKILL.md
  - docs/releases/2026-06-03-v0.1.3-release-evidence.md
  - docs/releases/2026-06-03-v0.1.3-dependency-inventory.md
---

# Development Log - Release Workflow

## Summary

Added a unified release workflow for version synchronization, changelog/dev-log/README/release-evidence updates, dependency inventory, dev commits, dev-to-main projection, and local tagging.

## Context

The project had multiple release version surfaces (`VERSION`, Python runtime version, package metadata, UI metadata, and run evidence). A stale `VERSION` file showed that release work needed a repeatable workflow rather than one-off edits.

## Changes

- Added `docs/engineering/release-process.md` as the release workflow source of truth.
- Added `.codex/skills/micro-eval-release/SKILL.md` to make the release workflow reusable by future agents.
- Added an `AGENTS.md` routing entry for version, changelog, release evidence, dependency inventory, tag, and dev-to-main release work.
- Added release scripts for version synchronization, version consistency checks, dependency inventory generation, and release preflight validation.
- Switched Python package metadata to Hatch dynamic versioning from `VERSION`.
- Generated v0.1.3 dependency inventory and release evidence.
- Sanitized dependency inventory tool checks so release artifacts do not persist absolute local executable paths or home-directory paths.
- Hardened `scripts/release-to-main.sh` so the temporary main worktree force-removes the explicit dev-only exclusion set after checking out source-branch content.

## Decisions

- `VERSION` is the single human-edited release version source.
- `pyproject.toml` reads the package version dynamically from `VERSION`.
- Historical version references in changelog, dev logs, archive, and specs remain unchanged.
- Dependency inventory records package/tool versions and external agent CLI availability without environment variables, tokens, account identifiers, or credential paths.
- Local annotated tags are allowed after maintainer approval; remote push remains opt-in and is not performed by default.

## Verification

- `python scripts/release/check-version-consistency.py --version 0.1.3`
- `uv run pytest -q tests/unit/test_version_consistency.py tests/unit/test_run_plan.py tests/unit/test_contract_fixture.py`
- `uv build`
- `python scripts/release/generate-dependency-inventory.py --version 0.1.3 --date 2026-06-03`

## Risks and follow-ups

- Future releases should run `scripts/release/preflight-release.sh` before committing; it checks both unstaged and staged whitespace errors.
- Browser storage grep remains a review signal, not a hard failure, unless product security rules change.
