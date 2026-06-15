---
title: Development Log - v0.1.1 Invocation Evidence
doc_type: dev_log
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-06-02T18:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - v0.1.1
  - invocation
  - evidence
related:
  - CHANGELOG.md
  - docs/_archive/invocation-evidence.md
  - docs/engineering/security-guidelines.md
---

# Development Log - v0.1.1 Invocation Evidence

## Summary

Added invocation evidence capture so each agent run could be explained through stdout, stderr, exit code, output artifacts, and structured failure information.

## Context

The initial MVP could compare outputs, but debugging and trust required stronger evidence around how an agent was invoked and what artifacts it produced.

## Changes

- Added stdout/stderr summaries and artifact references.
- Persisted invocation artifacts under `.micro-eval/artifacts/{run_id}/{task_id}--{agent_name}/`.
- Added bounded stdout/stderr capture with a retained-output cap.
- Added output artifact capture for file and directory output modes.
- Added environment allowlisting and output path environment variables.
- Added secret redaction coverage for agent environment values.

## Decisions

- Replace shell-based execution with argv-based subprocess execution.
- Preserve full retained artifacts on disk while exposing bounded summaries in run results.
- Keep this as a transition layer before the full canonical artifact model.

## Verification

Retrospective note based on release history. The changelog records focused runner and schema coverage for evidence fields, artifacts, timeout handling, and secret redaction.

## Risks and follow-ups

- Artifact paths still depended on `task_id--agent_name` and could collide for same-name agents.
- Run storage was still legacy flat JSON.
- Canonical `ArtifactRef`, `EvidenceItem`, `RunPlan`, and same-start evidence were still future work.
