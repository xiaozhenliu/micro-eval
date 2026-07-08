---
title: Dev Log - v0.4.3 Security Audit Release Preparation
doc_type: dev_log
status: active
created_at: 2026-07-08T15:14+08:00
updated_at: 2026-07-08T15:14+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev_log
  - release
  - security
related:
  - CHANGELOG.md
  - docs/releases/2026-07-08-v0.4.3-release-evidence.md
  - docs/releases/2026-07-08-v0.4.3-dependency-inventory.md
  - docs/engineering/release-process.md
---

# Dev Log - v0.4.3 Security Audit Release Preparation

## Context

The 2026-07-07 security audit (GRO-172~194) landed as individual reviewed
commits on `dev` but its CHANGELOG entries were still under `## Unreleased`, and
v0.4.2 had never been projected to `main`. This release cuts a dedicated 0.4.3
security patch, projects `dev` to `main`, and publishes.

## Actions

1. Ignored Playwright MCP runtime artifacts: added `.playwright-mcp/` to
   `.gitignore` (console/page logs are not project content). Untracked directory
   left on disk, no longer staged.
2. Version bump `0.4.2 -> 0.4.3` via `scripts/release/sync-version.py 0.4.3`
   (VERSION, `__init__.py`, README `Current version`, `ui/package.json`,
   `ui/package-lock.json`, `ui/src/lib/fixtures/canonical-run-p0.json`).
3. Manually aligned surfaces the sync script does not touch:
   `tests/contract/golden/run-p0-contract.json` tool_version, README/README.zh-CN
   version badges, and the README.zh-CN `当前版本` line.
4. CHANGELOG: moved the Unreleased security section under a new
   `## 0.4.3 - 2026-07-08` heading; kept an empty `## Unreleased` placeholder.
5. Generated dependency inventory (`v0.4.3`) and wrote release evidence.
6. Validation: 606 pytest, 114 vitest, ESLint clean, `next build` exit 0,
   `uv build` 0.4.3 wheel+sdist, version consistency pass, whitespace clean.
   Shell-injection grep only hits the guard test constants — no real shell use.

## Notes

- `preflight-release.sh`'s trailing `grep ... && exit 1` step matches the string
  constants inside `tests/contract/test_execution_contract.py`, so the wrapper
  script would false-fail. Individual preflight steps were run directly and the
  grep result inspected by hand (release-process.md treats greps as review
  signals, not unconditional failures). A future cleanup could exclude the guard
  test path from that grep; out of scope for this release.
