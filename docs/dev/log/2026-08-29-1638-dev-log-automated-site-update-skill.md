---
title: Development Log - Automated Site Update Skill
doc_type: dev_log
status: active
created_at: 2026-08-29T16:38+08:00
updated_at: 2026-08-29T16:38+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - agent-skills
  - documentation-site
  - automation
related:
  - .agents/skills/micro-eval-site/SKILL.md
  - .agents/skills/micro-eval-site/references/site-impact-map.toml
  - .agents/skills/micro-eval-site/scripts/site_update.py
  - .scratch/site-skill/issues/resolved/02-automate-site-update-from-changes.md
---

# Development Log - Automated Site Update Skill

## Summary

Upgraded `micro-eval-site` from project guidance into a three-layer executable
workflow: git impact analysis, agent-authored bilingual content updates, and an
independent fail-closed verification layer.

## Context

The initial skill described content authorities, bilingual parity, and build
expectations, but it did not inspect source changes or prove that an agent had
actually updated every affected content domain. A specification-only skill
could still stop after producing a plausible plan.

## Changes

- Added `site_update.py` with `plan`, `resolve`, and `verify` subcommands.
- Added a project impact map covering release metadata, CLI, configuration,
  tasks, result models, execution/sandboxing, evaluation, decisions/trends,
  storage, traces/cost, Team Server, Web UI, examples, and security guidance.
- Made planning include committed differences from a chosen base plus staged,
  unstaged, and untracked worktree paths.
- Added a resolution ledger requiring every matched rule to be marked
  `updated` or `no-doc-impact` with evidence.
- Made verification independently rescan git, validate plan freshness and rule
  coverage, require updated pages in the real diff, enforce locale pairing, and
  run VitePress plus mapped source contract tests.
- Added private behavior tests for impact mapping and verification failures.

## Decisions

- Keep change discovery, coverage, and command execution deterministic.
- Keep natural-language rewriting in the agent layer because arbitrary guide
  prose cannot be reliably regenerated from an AST or schema alone.
- Treat verifier success as necessary but not sufficient for semantic quality:
  it proves coverage, paired diffs, builds, and source contracts, while the
  agent remains responsible for comparing claims with current authority files.
- Fail closed when a new behavior path has no impact rule so the routing map
  cannot silently become stale.

## Verification

- The private site-update workflow test suite passed all 10 behavior tests.
- A real git-derived `plan` followed by `verify` completed with
  `"status": "verified"` and ran the VitePress 1.6.4 production build.
- The mapped CLI contract suite passed 28 tests.
- The mapped UI contract suite passed 115 tests across 12 files.
- Skill structure validation passed.
- Public projection, work governance, and diff checks are recorded in the
  resolved ticket after the final worktree verification.

## Risks and follow-ups

- The verifier cannot prove that two natural-language paragraphs are
  semantically equivalent; bilingual semantic review remains an agent task.
- A new source domain intentionally blocks strict planning until maintainers
  add its candidate pages and source checks to the impact map.
- Mapped source suites are proportional but may still require dependency setup
  or sandbox approval in a fresh environment.
