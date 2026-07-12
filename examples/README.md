---
title: micro-eval Examples
doc_type: tutorial
status: active
created_at: 2026-06-03T10:18+08:00
updated_at: 2026-07-08T00:00+08:00
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
  - examples/conversational-eval/README.md
  - examples/team-server-quickstart/README.md
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
| [Agent Codefix Showdown](agent-codefix-showdown/) | A complete run over one local code-fix task, with a real-agent matrix for Claude Code, Codex CLI, OpenClaw, and Hermes plus a deterministic mock smoke path. The mock path runs 3 repetitions with process trace capture, demonstrating Phase 2 pass@k aggregation, `decision.json`, and the review UI. **Blank variant** (`eval.blank.yaml`) adds `blank` workspace type + `input_mode: file`. |
| [Multi-Task Matrix](multi-task-matrix/) | 2 configs × 3 tasks × 2 reps = 12-cell matrix with all four expectation types (`exit_code`, `contains`, `file_exists`, `command`), workspace setup commands, and a deliberately partial-failing candidate. **Enriched variant** (`eval.enriched.yaml`) adds `randomize_execution_order`, `skills_profile`, `parameters`, `denominator_policy: exclude_failed`, and `stop_on_cell_error`. |
| [Git Workspace Isolation](git-workspace-isolation/) | `git_repo` workspace with per-cell git worktree isolation, OS policy sandbox (Seatbelt/Bubblewrap), fixture digest + toolchain fingerprint in `SameStartSnapshot`, and two-run trend analysis with a drift breakpoint. |
| [Conversational Evaluation](conversational-eval/) | Multi-turn conversation via DeepEval ConversationSimulator, JSONL subprocess bridge, all 5 conversational metrics, structured RubricSpec with dimensions. Requires DeepEval + LLM provider for scoring. |
| [Team Server Quickstart](team-server-quickstart/) | End-to-end `micro-eval serve` workflow: template management, workspace creation from template, HTTP API run enqueue (`/api/workspaces/{id}/runs/enqueue`) with member attribution, serial queue monitoring, and result inspection. Uses a deterministic mock agent. Requires `cd ui && npm run build` once. |

## Capability coverage matrix

`docs` = README provides a configuration snippet; no offline mock path exists for this capability.

| Capability | codefix-showdown | multi-task-matrix | git-workspace-isolation | conversational-eval | team-server |
|---|:---:|:---:|:---:|:---:|:---:|
| Matrix execution (Tasks × Configs × Reps) | ✓ | ✓ | ✓ | ✓ | |
| Multi-task | | ✓ | ✓ | ✓ | |
| `files` workspace | ✓ | ✓ | | | ✓ |
| `git_repo` workspace | | | ✓ | | |
| `blank` workspace | ✓ (eval.blank) | | | | |
| `exit_code` expectation | | ✓ | | | |
| `contains` expectation | ✓ | ✓ | ✓ | | ✓ |
| `file_exists` expectation | | ✓ | | | |
| `command` expectation | | ✓ | | | |
| `stdin` input mode | ✓ | ✓ | ✓ | ✓ | ✓ |
| `file` input mode | ✓ (eval.blank) | | | | |
| `stdout` output mode | | docs | ✓ | ✓ | |
| `file` output mode | ✓ | ✓ | | | ✓ |
| `directory` output mode | | docs | | | |
| `setup` commands | | ✓ | | | |
| Process trace | ✓ | ✓ | ✓ | ✓ | ✓ |
| OS policy sandbox | | | ✓ | | |
| Fixture digest | | | ✓ | | |
| Toolchain fingerprint | | | ✓ | | |
| Trend analysis + drift breakpoint | | | ✓ | | |
| pass@k / pass^k aggregation | ✓ | ✓ | ✓ | | |
| Caveat (real trigger) | | ✓ | ✓ | | |
| Human annotation guide | | | ✓ (README) | | |
| LLM Judge | | | docs | | |
| Langfuse trace | | | docs | | |
| Secrets channel | | | docs | | |
| E2B/Modal remote VM | | | docs | | |
| Conversational evaluation | | | | ✓ | |
| JSONL subprocess bridge | | | | ✓ | |
| Structured RubricSpec | | | | ✓ | |
| `randomize_execution_order` | | ✓ (enriched) | | | |
| `skills_profile` | | ✓ (enriched) | | | |
| `parameters` | | ✓ (enriched) | | | |
| `denominator_policy: exclude_failed` | | ✓ (enriched) | | | |
| `inconclusive_policy: block` | | ✓ (enriched) | | | |
| `stop_on_cell_error: true` | | ✓ (enriched) | | | |
| `micro-eval serve` | | | | | ✓ |
| Template management | | | | | ✓ |
| Workspace management | | | | | ✓ |
| HTTP API (evaluate) | | | | | ✓ |
| Member attribution | | | | | ✓ |
| Serial queue | | | | | ✓ |
| CSRF protection | | | | | ✓ |

## Quick start

From the repository root, run the deterministic smoke path with one
cross-platform Python command:

```bash
# Default: agent-codefix-showdown (backward compatible)
python examples/run-example.py

# Run a specific example
python examples/run-example.py --example multi-task-matrix
python examples/run-example.py --example git-workspace-isolation
python examples/run-example.py --example conversational-eval
python examples/run-example.py --example team-server-quickstart

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

### Config variants

Some examples ship multiple config files for different feature coverage:

```bash
# multi-task-matrix: enriched variant (randomize, skills_profile, etc.)
python examples/multi-task-matrix/run.py --variant enriched

# agent-codefix-showdown: blank workspace + file input mode
cd examples/agent-codefix-showdown && uv run micro-eval run --config eval.blank.yaml
```

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
