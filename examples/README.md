---
title: micro-eval Examples
doc_type: tutorial
status: active
created_at: 2026-06-03T10:18+08:00
updated_at: 2026-06-15T00:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - examples
  - onboarding
  - mvp
related:
  - examples/agent-codefix-showdown/README.md
  - examples/multi-task-matrix/README.md
  - examples/git-workspace-isolation/README.md
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
| [Multi-Task Matrix](multi-task-matrix/) | 2 configs × 3 tasks × 2 reps = 12-cell matrix with all four expectation types (`exit_code`, `contains`, `file_exists`, `command`), workspace setup commands, and a deliberately partial-failing candidate that produces an `inconclusive` decision (baseline all-pass vs candidate partial-fail). |
| [Git Workspace Isolation](git-workspace-isolation/) | `git_repo` workspace with per-cell git worktree isolation, OS policy sandbox (Seatbelt/Bubblewrap), fixture digest + toolchain fingerprint in `SameStartSnapshot`, and two-run trend analysis with a drift breakpoint. |

## Capability coverage matrix

`docs` = README provides a configuration snippet; no offline mock path exists for this capability.

| Capability | codefix-showdown | multi-task-matrix | git-workspace-isolation |
|---|:---:|:---:|:---:|
| Matrix execution (Tasks × Configs × Reps) | ✓ | ✓ | ✓ |
| Multi-task | | ✓ | ✓ |
| `files` workspace | ✓ | ✓ | |
| `git_repo` workspace | | | ✓ |
| `exit_code` expectation | | ✓ | |
| `contains` expectation | ✓ | ✓ | ✓ |
| `file_exists` expectation | | ✓ | |
| `command` expectation | | ✓ | |
| `stdout` output mode | | docs | ✓ |
| `file` output mode | ✓ | ✓ | |
| `directory` output mode | | docs | |
| `setup` commands | | ✓ | |
| Process trace | ✓ | | |
| OS policy sandbox | | | ✓ |
| Fixture digest | | | ✓ |
| Toolchain fingerprint | | | ✓ |
| Trend analysis + drift breakpoint | | | ✓ |
| pass@k / pass^k aggregation | ✓ | ✓ | ✓ |
| Caveat (real trigger) | | ✓ | ✓ |
| Human annotation guide | | | ✓ (README) |
| LLM Judge | | | docs |
| Langfuse trace | | | docs |
| Secrets channel | | | docs |
| E2B/Modal remote VM | | | docs |

## Quick start

From the repository root, run the deterministic smoke path with one
cross-platform Python command:

```bash
# Default: agent-codefix-showdown (backward compatible)
python examples/run-example.py

# Run a specific example
python examples/run-example.py --example multi-task-matrix
python examples/run-example.py --example git-workspace-isolation

# Run all examples sequentially
python examples/run-example.py --example all
```

The script uses `uv run --project` when `uv` is available and falls back to an
installed `micro-eval` command. It runs from the example directory so the run
store and `report.html` land under the respective example directory.

For real local agent CLIs (codefix-showdown only), use:

```bash
python examples/run-example.py --real
```

Start with the use case README if you need the manual command breakdown or the
security caveats.

## Advanced: Optional External Integrations

The capabilities below require external API keys or services. They cannot run
offline. Each example's `eval.mock.yaml` can be extended with the snippets below.

### LLM Judge (DeepEval)

Add to any `eval.yaml`:

```yaml
judge:
  enabled: true
  provider: deepeval
  model: "gpt-4o"
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_KEY]
```

Set the secret before running:

```bash
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
```

### Langfuse Trace

```yaml
trace:
  enabled: true
  provider: langfuse
```

Set credentials:

```bash
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

### Secrets Channel

Declare secrets in the agent spec:

```yaml
agent:
  required_secrets: [MICRO_EVAL_SECRET_MY_KEY]
```

micro-eval injects values from `MICRO_EVAL_SECRET_*` environment variables and
redacts them from all logs and traces.

### E2B / Modal Remote VM

Change the workspace isolation level in a task YAML:

```yaml
workspace:
  isolation_level: vm
  trust_level: untrusted
```

Set credentials:

```bash
export E2B_API_KEY=e2b_...
# or
export MODAL_TOKEN_ID=...
export MODAL_TOKEN_SECRET=...
```

Note: without credentials, remote VM providers fail hard (no silent downgrade).
