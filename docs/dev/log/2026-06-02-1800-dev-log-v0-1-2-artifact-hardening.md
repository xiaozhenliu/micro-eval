---
title: Development Log - v0.1.2 Artifact Hardening
doc_type: dev_log
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-06-02T18:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - v0.1.2
  - artifacts
  - hardening
related:
  - CHANGELOG.md
  - docs/engineering/security-guidelines.md
---

# Development Log - v0.1.2 Artifact Hardening

## Summary

Hardened run IDs and invocation artifact paths, and fixed UI hydration issues so the local workflow became more stable and easier to inspect.

## Context

After adding invocation evidence, the next risk was artifact collision and confusing run identifiers, especially when baseline and candidate agents shared the same name.

## Changes

- Generated readable, collision-resistant run IDs with timestamp plus random suffix.
- Added baseline/candidate role labels to invocation artifact paths.
- Preserved the legacy flat `.micro-eval/runs/{run_id}.json` shape while improving artifact references.
- Fixed `AnnotationPanel` local storage hydration so UI lint could pass without changing the annotation workflow.
- Added regression coverage for artifact path uniqueness, run IDs, readable refs, file/directory artifacts, redaction, and timeout handling.

## Decisions

- Keep the storage shape stable for this patch rather than migrating to the full canonical run directory layout.
- Fix the highest-risk evidence and UI issues before broader model changes.

## Verification

Retrospective note based on release history. The changelog records regression coverage for artifact paths, run IDs, artifact refs, redaction, and timeout behavior.

## Risks and follow-ups

- Canonical run layout and configuration matrix planning were still open.
- Human evaluation was still local UI state rather than persisted evidence.
- Same-start snapshots and replay evidence were still future work.
