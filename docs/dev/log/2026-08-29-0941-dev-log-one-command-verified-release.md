---
title: Development Log - One-command Verified Release
doc_type: dev_log
status: active
created_at: 2026-08-29T09:41+08:00
updated_at: 2026-08-29T09:54+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - release
  - security
related:
  - scripts/release-to-main.sh
  - scripts/release/public_projection.py
  - scripts/release/public-projection.toml
  - docs/engineering/release-process.md
  - docs/engineering/security-service-guidelines.md
---

# Development Log - One-command Verified Release

## Summary

Release staging is now one local-only command with a small interface and a deep
Release Module. Candidate gates finish before local `main` moves. Publishing is
a separate exact-SHA action that rejects public `dev` and can atomically publish
an annotated version tag for the same verified commit.

## Context

The fail-closed public projection already prevented private paths and package
entries from entering `main`, but two stability gaps remained. Local `main`
moved before candidate tests completed, and the documented manual tag command
could tag the active private `dev` commit. A public repository also has no
private branches, so publication must reject a public remote containing `dev`.

## Changes

- Added `stage` and `publish` command forms while retaining local-only
  compatibility flags.
- Kept candidate commits under a private local Git ref with a `staged` receipt;
  verification uses compare-and-swap to move `main` only after all gates pass.
- Added safe retry behavior after candidate failure.
- Added public remote inspection that aborts publication when `dev` exists.
- Added optional version-bound annotated tags and atomic `main` plus tag push.
- Removed public CI's `dev` push trigger and synchronized Skill, generated
  `AGENTS.md`, release documentation, security guidance, and regression tests.

## Decisions

- “One command” means one command to produce a verified local public release;
  remote mutation remains a second explicit authorization.
- Skill is an operational guide. Policy, candidate construction, receipts,
  exact-SHA publication, and tag invariants remain executable Module gates.
- The public remote may contain projected `main` and approved release tags, but
  never private `dev`, `--all`, or `--mirror` output.

## Verification

- Focused release coverage passed with 26 tests. It exercises successful and
  idempotent stage, candidate failure with unchanged `main`, safe retry,
  invalid/missing release evidence, unknown/private paths, missing/stale/
  unverified receipts, public `dev` rejection, wrong/lightweight tags, exact
  main publication, annotated tag publication, and atomic remote failure.
- `scripts/release/preflight-release.sh 0.4.5` passed: version and release
  evidence consistency, fail-closed path planning, compilation, 653 Python
  tests, UI lint, 115 UI tests, UI production build, wheel/sdist build, archive
  validation, diff checks, and shell safety gates.
- The final worktree plan classifies 420 public, 87 private, and 2 generated
  paths; the candidate public tree contains 422 paths.
- The verified sdist contains 76 entries and the wheel contains 73 entries.
- ShellCheck, Python byte compilation, generated `AGENTS.md` equality, CI YAML
  parsing, and `git diff --check` passed.
- No project branch or tag was pushed. Remote publication tests used only
  temporary bare Git repositories.

## Risks and follow-ups

- Git remotes cannot make a branch private inside a public repository. If a
  shared remote for full `dev` becomes necessary, it must be a separate private
  repository.
- PyPI or GitHub Release publication remains out of scope; future publishers
  must consume the verified artifact hashes rather than rebuilding packages.

## Security review

- All trusted Python subprocess calls remain argv-only; no shell interpolation
  was introduced.
- Receipts store Git identities, policy/artifact hashes, status, and remote/tag
  names only; they do not persist environment variables, credentials, or file
  contents.
- This Module operates only on repository release worktrees and Git refs. It
  does not change evaluation workspace, raw artifact, redaction, UI, or API
  behavior.
