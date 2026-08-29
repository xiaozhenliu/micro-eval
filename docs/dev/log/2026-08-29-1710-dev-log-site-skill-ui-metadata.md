---
title: Development Log - Site Skill UI Metadata
doc_type: dev_log
status: active
created_at: 2026-08-29T17:10+08:00
updated_at: 2026-08-29T17:10+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - agent-skill
  - project-site
related:
  - .agents/skills/micro-eval-site/SKILL.md
  - .agents/skills/micro-eval-site/agents/openai.yaml
  - .scratch/site-skill/issues/resolved/03-complete-skill-ui-metadata.md
---

# Development Log - Site Skill UI Metadata

## Summary

The private `micro-eval-site` skill now includes OpenAI product metadata for a
user-facing name, short description, default prompt, and implicit invocation
policy. Its standard `SKILL.md` description, three-layer update workflow, and
cross-agent canonical sharing remain unchanged.

## Context

The Agent Skills format requires `name` and `description` in `SKILL.md`; the
existing skill already satisfied that contract. OpenAI additionally supports
optional `agents/openai.yaml` metadata for skill-list presentation and
invocation policy. That optional layer was missing after the functional site
automation work and was the remaining item from the format review.

## Changes

- Generated `.agents/skills/micro-eval-site/agents/openai.yaml` with the
  official skill-creator helper.
- Added `display_name`, a 54-character `short_description`, and a one-sentence
  `default_prompt` that explicitly invokes `$micro-eval-site`.
- Kept `allow_implicit_invocation: true` so repository changes that affect the
  public site can continue to select the skill automatically.

## Decisions

- No icon, brand color, or dependency field was added because the skill has no
  maintained visual asset or required MCP server.
- `.agents/skills/micro-eval-site` remains the canonical copy. The Claude and
  Codex discovery paths continue to be symbolic links to that directory.
- Product-specific metadata stays under `agents/`; non-OpenAI agents can ignore
  it while continuing to consume the standard `SKILL.md` and supporting files.

## Verification

- OpenAI `quick_validate.py` accepted the canonical skill and both symbolic
  link entry points.
- Agent Skills `agentskills validate` accepted the canonical skill.
- An independent YAML contract check verified the exact top-level keys,
  25–64-character short description, `$micro-eval-site` default prompt,
  implicit-invocation boolean, and absence of unsupported presentation fields.
- Both client-specific paths resolved and exposed the generated metadata file.
- The existing site skill behavior suite passed all 10 tests.
- Work governance, cached and unstaged diff checks, and a staged-tree public
  projection plan passed after the final ticket and log update.

## Security

- The metadata contains no credentials, external tool dependency, executable
  path, or network endpoint.
- The skill remains under paths classified as private by the public projection
  policy, so the metadata and development records do not enter public `main`.

## Risks and follow-ups

- `agents/openai.yaml` is OpenAI-specific optional metadata. Its UI rendering
  may evolve independently of the Agent Skills core format; the standard
  `SKILL.md` remains the cross-agent source of behavior and discovery scope.
