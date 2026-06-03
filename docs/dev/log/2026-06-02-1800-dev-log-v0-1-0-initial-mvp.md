---
title: Development Log - v0.1.0 Initial MVP
doc_type: dev_log
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-06-02T18:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - dev-log
  - v0.1.0
  - mvp
related:
  - CHANGELOG.md
  - docs/DEVELOPMENT.md
---

# Development Log - v0.1.0 Initial MVP

## Summary

Delivered the first local MVP of `micro-eval`: a Python CLI, a basic async execution path, JSON run output, HTML report generation, and a local Next.js UI for pairwise baseline/candidate comparison.

## Context

This slice established the smallest usable evaluation workflow: configure tasks and agents, run a baseline/candidate comparison, store results, and inspect the outcome locally.

## Changes

- Added the initial CLI and local Web UI.
- Added baseline/candidate pairwise evaluation from YAML configuration.
- Added task loading, subprocess execution, exact/contains scoring, JSON run output, and static HTML report generation.
- Added initial run list and comparison views in the UI.

## Decisions

- Start with a local-first MVP instead of a hosted platform.
- Keep execution self-owned and simple.
- Treat the UI as a local inspection surface over `.micro-eval/` artifacts.

## Verification

Retrospective note based on release history. Detailed verification evidence was not yet separated into a release evidence document for this version.

## Risks and follow-ups

- Execution evidence was still minimal.
- Run storage was still a legacy flat JSON shape.
- Reproducibility and same-start evidence were not yet captured.
