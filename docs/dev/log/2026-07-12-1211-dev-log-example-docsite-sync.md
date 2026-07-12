---
title: Development Log - Example Docsite Sync
doc_type: dev_log
status: active
created_at: 2026-07-12T12:11+08:00
updated_at: 2026-07-12T12:11+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - examples
  - documentation
related:
  - examples/README.md
  - site/examples/index.md
  - site/zh/examples/index.md
  - docs/superpowers/plans/2026-07-12-example-docsite-sync-plan.md
---

# Development Log - Example Docsite Sync

## Summary

Synchronized the English and Chinese docs-site example indexes with the current source-checkout example inventory.

## Context

The docs site listed 3 examples, while `examples/README.md` and `examples/run-example.py` listed 5. The approved plan described 40 capabilities, but the source matrix contained 43 rows at implementation time.

## Changes

- Added `conversational-eval` and `team-server-quickstart` launcher commands.
- Expanded both available-example tables from 3 to 5 entries.
- Mirrored all 43 source capability rows across 5 example columns.
- Added `eval.enriched.yaml` and `eval.blank.yaml` config variant commands.

## Decisions

- Treat `examples/README.md` as the inventory and capability source of truth, including its current 43-row matrix.
- Link the two new example entries to the existing conversational evaluation and Team Server guides instead of creating duplicate docs-site pages.

## Verification

- Confirmed both docs-site matrices contain 43 capability rows.
- Confirmed both indexes reference all 5 examples and both config variants.
- Ran `npm run docs:build` successfully from `site/`.

## Risks and follow-ups

- The capability count can drift when the matrix changes. A future documentation task may generate the docs-site matrix from structured example metadata or validate it automatically.
- Dedicated docs-site pages for the two new examples remain optional; the existing guide links cover their concepts without duplicating content.
