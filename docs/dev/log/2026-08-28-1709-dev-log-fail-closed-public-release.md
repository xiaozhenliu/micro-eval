---
title: Development Log - Fail-closed Public Release
doc_type: dev_log
status: completed
created_at: 2026-08-28T17:09+08:00
updated_at: 2026-08-28T17:29+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - release
  - security
related:
  - scripts/release/public-projection.toml
  - scripts/release/public_projection.py
  - scripts/release-to-main.sh
  - docs/engineering/release-process.md
  - docs/engineering/security-service-guidelines.md
---

# Development Log - Fail-closed Public Release

## Summary

The release flow now treats the public repository tree and Python archives as
allowlisted outputs. Every tracked source path must be public, private, or
generated; unknown and conflicting paths fail closed. Local projection and
remote push are separate operations joined by a policy-bound verified receipt.

## Context

The previous merge-then-strip blacklist had repeated path-list drift and leak
repairs. A newly tracked `CONTEXT.md` path was not classified, a root Vitest
cache remained tracked on both branches, and a local preflight sdist included
697 entries including 197 untracked local files.

## Changes

- Added the single public/private/generated policy and a Python projection
  Module that constructs `main` from an empty candidate index in an isolated
  worktree.
- Generated public `AGENTS.md` and `.gitignore` from explicit sources and made
  old `main`-only leaks disappear unless the policy restores them.
- Added sensitive-path, private-key marker, symlink, archive traversal, and
  wheel/sdist entry checks.
- Added explicit Hatch sdist inputs; the resulting local sdist fell from 697 to
  76 verified entries and no longer includes internal or untracked work files.
- Removed the tracked root `node_modules/.vite` result and ignored root
  `node_modules`, `.omx`, `.scratch`, and `.superpowers` runtime paths.
- Added local verified receipts and a separate push-only command requiring the
  exact full candidate SHA.
- Added CI classification and artifact gates plus real Git/bare-origin
  integration coverage.

## Decisions

- The allowlist decides publication. Deny patterns are defense in depth only.
- Unknown or multiply classified tracked paths abort instead of being silently
  published or silently omitted.
- `CONTEXT.md` is internal domain-language material and is classified private.
- Release artifacts are built from the candidate public tree; preflight/CI also
  verify explicit archive allowlists.
- Push authorization applies only to the exact SHA in a current verified local
  receipt and never implies permission to push `dev` or tags.

## Verification

- `scripts/release/preflight-release.sh 0.4.5` passed end to end: version
  consistency, path classification, compile checks, 645 Python tests, UI lint,
  UI production build, Python package build, archive validation, and diff/shell
  safety gates.
- Focused policy/release coverage passed with 18 tests, including unknown and
  conflicting paths, sensitive content, malicious archive entries, generated
  file equality, historical leak removal, stale SHA, missing/unverified receipt,
  local-only behavior, and a push to a temporary bare Git origin.
- The final plan classified 420 public, 86 private, and 2 generated paths. The
  candidate public tree contains 422 paths.
- The verified sdist contains 76 entries and the wheel contains 73 entries.
  Their SHA-256 hashes are `b51b884eaa2340c1dfa66b7190f016cbb5dba8e9dc1fdd8f95c963fef2673a4d`
  and `8fdbdc951a01639ee3f10f9de19a1f7a34e3ce488494c26178fc266b9fc30c9e`.
- `git diff --check`, ShellCheck, Python byte compilation, CI YAML parsing, and
  generated `AGENTS.md` template equality all passed.
- No project remote branch or tag was pushed. Push coverage used only a
  temporary test repository and bare origin.

## Risks and follow-ups

- The policy is intentionally fail closed, so legitimate new top-level paths
  require explicit classification before release.
- Receipts live under the Git common directory and are local verification state;
  release evidence should record the verified SHA and artifact hashes.

## Security review

- Git and build subprocesses use argv-only calls; no `shell=True` or shell
  interpolation was added to trusted Python paths.
- The projection reads only committed Git blobs and explicit generated sources;
  ignored/untracked local work files cannot enter the candidate tree.
- Receipt and archive validation do not read or persist credentials. Private-key
  markers and sensitive paths cause failure without echoing file contents.
- Evaluation workspace, artifact manifest, redaction, and UI/API behavior are
  unchanged by this release-tooling Module.
