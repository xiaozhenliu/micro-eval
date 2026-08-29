---
title: Development Log - Monid Free Search Skill
doc_type: dev_log
status: active
created_at: 2026-08-29T17:00+08:00
updated_at: 2026-08-29T17:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - agent-skill
  - search
related:
  - .agents/skills/monid/SKILL.md
  - .scratch/monid/issues/resolved/01-install-private-free-search-skill.md
---

# Development Log - Monid Free Search Skill

## Summary

The repository now has one private, project-scoped Monid skill for live web
search and page fetching. Its default project policy permits a Monid run only
when the exact TinyFish endpoint has just been inspected and its current price
is explicitly zero.

## Context

The requested capability was free search available to multiple agent clients,
not merely a document that described a possible integration. The remote Monid
skill also needed two local compatibility corrections: its top-level `version`
field was not accepted by the strict OpenAI skill validator, and its examples
claimed that CLI 0.1.6 supported `monid runs get -o` even though the installed
CLI rejects that option.

## Changes

- Added `.agents/skills/monid` as the canonical project skill and linked the
  Claude and Codex discovery locations to that single copy.
- Preserved the Monid version as `metadata.version`, added Codex-facing
  `agents/openai.yaml` metadata, and kept implicit invocation enabled.
- Added a repository policy that allows ordinary Monid search/fetch runs only
  through a currently zero-priced TinyFish endpoint. Unknown or nonzero prices
  require another free tool or explicit user authorization.
- Corrected output-persistence guidance for CLI 0.1.6: direct files use
  `monid run --wait -o`; completed async runs use `monid runs get -j` and the
  host agent's file-writing capability.
- Installed Monid CLI 0.1.6 and completed its machine-local setup. Credentials
  remain in Monid's user configuration and are not stored in this repository.

## Decisions

- `.agents/skills/monid` is the canonical cross-agent copy. Client-specific
  directories contain symbolic links so the instructions cannot drift.
- “Free” is determined from live `discover` and `inspect` price data, not from
  marketing text or a cached assumption.
- API keys and transient search output stay outside the repository. Validation
  records only boolean authentication success, endpoint identity, HTTP status,
  price, cost, and billed units.

## Verification

- `monid --version` reported 0.1.6, matching `metadata.version`.
- `monid keys list -j` confirmed an active key without exposing its value.
- `monid discover` returned verified, healthy `tinyfish/search` and
  `tinyfish/fetch` entries at `$0/call`; nonzero alternatives were excluded.
- `monid inspect -p tinyfish -e /search -j` confirmed query parameters,
  verified status, healthy metrics, and `$0/call` immediately before use.
- Two live TinyFish smoke searches completed with HTTP 200, reported cost `$0`,
  and zero billed units. The second used `monid run --wait -o`, and its JSON
  output was parsed successfully from a system temporary directory.
- OpenAI `quick_validate.py` and Agent Skills `agentskills validate` accepted
  the canonical skill; the client-specific symbolic links resolve to it.
- The staged-tree public projection plan classified all `.agents/**`,
  `.claude/**`, and `.codex/**` paths as private and produced no unknown path.
- Work-governance passed on the current working tree; both cached and unstaged
  diff checks were clean after the skill and ticket updates.

## Security

- No API key value, credential path, environment dump, or search payload was
  written to tracked files or emitted in validation evidence.
- Search output was written only to a system temporary directory. No runtime
  output entered the agent workspace or release projection.
- No product subprocess implementation changed. Repository edits are skill and
  development records only; shell interpolation and product workspace
  boundaries are unchanged.

## Risks and follow-ups

- Endpoint prices and CLI flags are external state. Every first use in a
  session must repeat `discover` and `inspect`; future skill refreshes must
  preserve the repository's zero-price guard and recheck CLI help.
