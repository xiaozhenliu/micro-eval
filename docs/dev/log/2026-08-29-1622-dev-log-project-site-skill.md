---
title: Development Log - Project Site Skill
doc_type: dev_log
status: active
created_at: 2026-08-29T16:22+08:00
updated_at: 2026-08-29T16:22+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - agent-skills
  - documentation-site
related:
  - .agents/skills/micro-eval-site/SKILL.md
  - .scratch/site-skill/issues/resolved/01-create-project-site-skill.md
  - scripts/release/public-projection.toml
---

# Development Log - Project Site Skill

## Summary

Added one project-specific Agent Skill for maintaining the bilingual VitePress
site, with a vendor-neutral canonical path and compatibility links for Claude
Code and Codex.

## Context

The available generic VitePress skill explains the framework but does not
encode micro-eval's content authorities, bilingual layout, navigation rules,
GitHub Pages boundary, or private development/public projection split. Those
project-specific constraints were being rediscovered for every site update.

## Changes

- Added the canonical skill at `.agents/skills/micro-eval-site/SKILL.md`.
- Added relative compatibility links under `.claude/skills/` and
  `.codex/skills/`, both resolving to the canonical skill.
- Narrowed the development `.gitignore` rule so the Claude compatibility link
  is tracked while other `.claude` state remains ignored.
- Documented authoritative source selection, English/Chinese parity,
  information architecture, navigation and base-path handling, and
  proportional verification.

## Decisions

- Keep one vendor-neutral skill source instead of copying instructions into
  agent-specific directories.
- Keep automatic invocation enabled because ordinary requests to update the
  project site should discover the skill without requiring a memorized name.
- Reuse the existing private classifications for `.agents/**`, `.claude/**`,
  and `.codex/**`; no release-policy change is required.

## Verification

- `quick_validate.py .agents/skills/micro-eval-site` passed.
- Validation through both compatibility links passed.
- `npm run docs:build` passed with VitePress 1.6.4. The existing large-chunk
  advisory remained non-fatal.
- `public_projection.py plan --source WORKTREE --json` passed with 425 public,
  108 private, and 2 generated paths; the skill paths were covered by the
  existing private patterns.
- `scripts/check-work-governance.py` and `git diff --check` passed.

## Risks and follow-ups

- A running agent session may need to reload skills or start a new session
  before discovering the new project skill.
- Agent tools that do not implement the Agent Skills standard still require
  their own integration; the canonical `.agents/skills` path covers the
  interoperable project-level contract, with the known Claude exception linked
  explicitly.
