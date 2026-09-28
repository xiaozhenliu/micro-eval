---
title: micro-eval Development Security Guidelines
language: en
authoritative: true
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-09-27T16:00+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - development
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/python-guidelines.md
  - docs/engineering/frontend-guidelines.md
  - docs/engineering/testing-guidelines.md
---

# micro-eval Development Security Guidelines

This file constrains the security requirements that developers and agents must follow when changing `micro-eval`'s own code.

## Subprocess and Shell

- Trusted execution paths never use shell interpolation.
- subprocess calls are argv-only.
- User input, task input, expected output, and agent commands are never assembled into shell strings for execution.

## Env and Secret Handling

- Host environment inheritance must be allowlisted.
- Secret injection is bounded by what a Configuration declares.
- Any textual evidence that will be persisted or returned to the UI/API must pass redaction first.
- When adding evidence, artifact, report, or UI/API output paths, re-check secret leakage risk.

## Workspace and Artifact Handling

- The agent cwd is the assigned workspace.
- The assigned workspace lives under the current eval project's `.micro-eval/workspaces/{run_id}/{cell_id}/`; the agent cwd never goes to a system temp directory or outside the project without explicit user configuration.
- Adapters / runners never write outside the workspace and run-artifact boundaries.
- Artifacts reach the UI/API only through the manifest/ref boundary.
- Symlink, hardlink, binary, oversized, and path-traversal artifact risks must be rejected, degraded, or explicitly recorded as warnings.

## Decision Safety

- Every signal affecting comparability must enter the snapshot / caveats / decision evidence.
- On snapshot mismatch, missing evidence, or untrusted artifacts, no strong conclusion may be produced.

## Verification and Review

For implementation changes, check at least:

- Was shell interpolation introduced?
- Could secrets leak?
- Was the workspace boundary bypassed?
- Was the agent cwd moved outside the current eval project?
- Are raw artifacts exposed directly to Decision / UI?
- Can a snapshot mismatch still produce a strong conclusion?
- Are negative tests or equivalent security verification missing?

The delivery report must state:

- how secrets redaction is handled;
- how the workspace boundary is handled;
- how shell interpolation is avoided.
