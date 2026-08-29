---
title: Development Log - Work Tracking Governance
doc_type: dev_log
status: active
created_at: 2026-08-29T12:39+08:00
updated_at: 2026-08-29T13:10+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - governance
  - ticket
related:
  - docs/agents/issue-tracker.md
  - docs/agents/triage-labels.md
  - TODOS.md
  - scripts/check-work-governance.py
  - .scratch/work-governance/issues/01-rebuild-work-tracking-governance.md
---

# Development Log - Work Tracking Governance

## Summary

Rebuilt the development work model around one Work Register, one authority
source per committed effort, durable local tickets, and explicit completion
evidence. Public documentation now describes the boundary without linking to
records omitted from the public projection.

## Context

The previous Register mixed stale completed work, future options, triage roles,
priority labels, and ticket lifecycle states. Local work records were also
ignored by Git, while public agent documentation pointed at paths that are
intentionally private.

## Changes

- Implementation commit: `c72b18814a29ffc83455c64a212fcf89fe807952`.
- Replaced the old Ready/Blocked/Done list with `Now`, `Next`, `Waiting`,
  `Roadmap`, and `Inbox` portfolio lanes.
- Expanded the Roadmap after audit to retain each genuine future item from the
  previous Register, including schema generation, CLI/provider coverage, task
  scope, three cost paths, run-wide controls, SQLite, OpenHands, and Windows.
- Added the `GH-15` pointer and moved conditional future work into Roadmap
  entries with explicit triggers.
- Removed the root `.scratch/` ignore rule, added durable effort maps, and
  normalized the existing next-release tickets to stable IDs and `resolved`
  completion evidence.
- Separated `Triage`, `Executor`, and lifecycle `Status` in the public agent
  contracts and release-generated agent instructions.
- Added an offline `scripts/check-work-governance.py` verifier and regression
  tests for pointers, lifecycle aliases, and public projection classification.

## Decisions

- Local tickets are the default for internal work; GitHub Issues are reserved
  for public feedback or collaboration.
- A non-trivial behavior, schema, security, release, or multi-file change is
  ticket-first. Trivial one-file corrections may proceed without a ticket.
- `resolved` is the only normal terminal spelling. Completion moves the work
  out of `TODOS.md` while retaining the ticket and its evidence.
- `.scratch/**` remains tracked on `dev` but private and forbidden in public
  output, package archives, and the public remote projection.

## Verification

- `uv run python scripts/check-work-governance.py` — passed.
- Focused governance and projection tests — passed: 13 tests.
- `uv run pytest tests/integration/test_release_to_main.py -q` — passed: 18 tests.
- Full release preflight — passed: 658 Python tests, 115 UI tests, UI lint/build,
  wheel/sdist allowlists, version consistency, projection plan, and shell-safety
  gates. The existing Turbopack NFT tracing warning did not prevent the build.
- `uv run python scripts/release/public_projection.py plan --source WORKTREE --json` — passed with 425 public, 103 private, 2 generated, and 427 candidate paths.
- `git check-ignore` returned no match for the governance ticket; `git ls-files .scratch/` listed all 15 durable work-record files.
- `git diff --check` and `git diff --cached --check` — passed.

## Risks and follow-ups

- A future Work Register change must add its stable pointer and ticket fields
  before implementation; the governance verifier is intentionally offline and
  does not validate GitHub open/closed state.
- The final repository commit and any later public projection remain governed
  by the normal `dev` release workflow and its verified receipt gates.
