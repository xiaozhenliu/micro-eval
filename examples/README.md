---
title: micro-eval Examples
doc_type: tutorial
status: active
created_at: 2026-06-03T10:18+08:00
updated_at: 2026-06-12T20:20+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - examples
  - onboarding
  - mvp
related:
  - examples/agent-codefix-showdown/README.md
  - docs/documentation-standard.md
---

# micro-eval examples

## Source-checkout examples

This directory contains source-checkout examples for `micro-eval`.

> Scope note: examples are repository/source assets for this MVP. They are not
> currently bundled into the wheel, and the Next.js UI assets are still launched
> from a source checkout.

## Available use cases

| Use case | What it demonstrates |
| --- | --- |
| [Agent Codefix Showdown](agent-codefix-showdown/) | A complete run over one local code-fix task, with a real-agent matrix for Claude Code, Codex CLI, OpenClaw, and Hermes plus a deterministic mock smoke path. The mock path runs 3 repetitions with process trace capture, demonstrating Phase 2 pass@k aggregation, `decision.json`, and the review UI. |

## Quick start

From the repository root, run the deterministic smoke path with one
cross-platform Python command:

```bash
python examples/run-example.py
```

The script uses `uv run --project` when `uv` is available and falls back to an
installed `micro-eval` command. It runs from the example directory so the run
store and `report.html` land under `examples/agent-codefix-showdown/`.

For real local agent CLIs, use:

```bash
python examples/run-example.py --real
```

Start with the use case README if you need the manual command breakdown or the
security caveats.
