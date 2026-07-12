# Examples

micro-eval ships 5 source-checkout examples covering 43 tracked capabilities, from deterministic matrix runs and sandboxed workspace isolation to conversational scoring and the Team Server workflow.

::: tip Source-checkout examples
Examples live in the repository under `examples/` and are not bundled into the wheel. Clone the repo before running them.
:::

## Quick Start

Run any example from the repository root using the cross-platform launcher:

::: code-group

```bash [Default (codefix-showdown)]
python examples/run-example.py
```

```bash [Specific example]
python examples/run-example.py --example multi-task-matrix
python examples/run-example.py --example git-workspace-isolation
python examples/run-example.py --example conversational-eval
python examples/run-example.py --example team-server-quickstart
```

```bash [All examples]
python examples/run-example.py --example all
```

```bash [Real local agent CLIs]
# codefix-showdown only — requires Claude Code, Codex CLI, etc.
python examples/run-example.py --real
```

:::

The launcher uses `uv run --project` when `uv` is available and falls back to an installed `micro-eval` command. Run output and `report.html` land under the respective example directory.

## Available Examples

| Example | What it demonstrates | Key capabilities |
|---|---|---|
| [Agent Codefix Showdown](/examples/agent-codefix-showdown) | Complete local code-fix run with real-agent and deterministic mock paths | `files` workspace, 3 repetitions, process trace, pass@k; `eval.blank.yaml` adds `blank` workspace and `input_mode: file` |
| [Multi-Task Matrix](/examples/multi-task-matrix) | 2 configs × 3 tasks × 2 reps = 12 cells with a deliberately partial-failing candidate | All 4 expectation types and setup commands; `eval.enriched.yaml` adds advanced execution and decision fields |
| [Git Workspace Isolation](/examples/git-workspace-isolation) | Per-cell `git_repo` worktree isolation and two-run trend analysis | OS policy sandbox, fixture digest, toolchain fingerprint, drift breakpoint |
| [Conversational Evaluation](/guide/conversational-evaluation) | Multi-turn scoring through DeepEval's ConversationSimulator | JSONL subprocess bridge, 5 conversational metrics, structured RubricSpec; requires DeepEval and an LLM provider |
| [Team Server Quickstart](/guide/team-server) | End-to-end `micro-eval serve` workflow using a deterministic mock agent | Templates, workspaces, HTTP enqueue, member attribution, serial queue; requires one `cd ui && npm run build` |

## Capability Coverage Matrix

Use this matrix to find the example that demonstrates the feature you want to learn about.

`docs` = the README provides a configuration snippet; no offline mock path exists for this capability.

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

## Config Variants

Config variants extend feature coverage without adding more example directories:

```bash
# multi-task-matrix: advanced execution and decision fields
python examples/multi-task-matrix/run.py --variant enriched

# agent-codefix-showdown: blank workspace and file input mode
cd examples/agent-codefix-showdown && uv run micro-eval run --config eval.blank.yaml
```

## Optional External Integrations

The capabilities below require external API keys or services and cannot run offline. Add the relevant snippet to any example's `eval.yaml` to enable them. See each example's README for the full context.

### LLM Judge (DeepEval)

```yaml
judge:
  enabled: true
  provider: deepeval
  model: "gpt-4o"
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_KEY]
```

```bash
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
```

### Langfuse Trace

```yaml
trace:
  enabled: true
  provider: langfuse
```

```bash
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

### Secrets Channel

Declare secrets in your agent spec and micro-eval will inject the values at runtime, redacting them from all logs and traces automatically:

```yaml
agent:
  required_secrets: [MICRO_EVAL_SECRET_MY_KEY]
```

All secrets must be prefixed `MICRO_EVAL_SECRET_` in the environment. See [Git Workspace Isolation](/examples/git-workspace-isolation) for a worked example.

### E2B / Modal Remote VM

Upgrade any task's isolation level to `vm` for full remote sandbox execution:

```yaml{3-4}
workspace:
  type: git_repo
  isolation_level: vm
  trust_level: untrusted
```

```bash
export E2B_API_KEY=e2b_...
# or
export MODAL_TOKEN_ID=...
export MODAL_TOKEN_SECRET=...
```

::: warning No silent downgrade
Remote VM providers (`E2B`, `Modal`) fail hard when credentials are missing. There is no automatic fallback to a lower isolation level — this is intentional to prevent undetected environment drift.
:::
