# Examples

micro-eval ships a set of source-checkout examples that cover the full capability surface of the tool — from a simple single-task smoke test through multi-cell matrices and Phase 3 sandboxed workspace isolation.

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
| [Agent Codefix Showdown](/examples/agent-codefix-showdown) | Complete MVP flow with a real-agent matrix | `files` workspace, argv commands, Phase 2 trace, pass@k |
| [Multi-Task Matrix](/examples/multi-task-matrix) | 2 × 3 × 2 = 12-cell matrix | All 4 expectation types, setup commands, `inconclusive` decision |
| [Git Workspace Isolation](/examples/git-workspace-isolation) | Phase 3 workspace + trend analysis | git worktree, OS sandbox, fixture digest, trend drift |

## Capability Coverage Matrix

Use this matrix to find the example that demonstrates the feature you want to learn about.

`docs` = the README provides a configuration snippet; no offline mock path exists for this capability.

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
| Human annotation guide | | | ✓ |
| LLM Judge | | | docs |
| Langfuse trace | | | docs |
| Secrets channel | | | docs |
| E2B/Modal remote VM | | | docs |

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
