# Execution

::: tip Where you are in the decision loop  
A **Run** expands Tasks × Configurations × Repetitions into a matrix of **Cells**, executes them, and produces a **ResultMatrix**.
See [Design System](./design-system#the-decision-loop) for the full pipeline.
:::

micro-eval evaluates agents by expanding a declarative configuration into a matrix of isolated runs, executing each cell concurrently, and collecting structured results. This page explains exactly how that pipeline works — from YAML to `ResultMatrix`.

## Execution Pipeline Overview

When you run `micro-eval run`, the engine performs these stages in order:

1. **Parse & validate** — load `eval.yaml`, apply Pydantic schema validation
2. **Matrix expansion** — decompose `Tasks × Configurations × Repetitions` into `RunCell` objects
3. **Plan recording** — write the `RunPlan` to `.micro-eval/runs/<run-id>/plan.json` before any cell executes
4. **Bounded concurrent execution** — dispatch cells via asyncio with a configurable concurrency cap
5. **Per-cell lifecycle** — prepare workspace → run agent → capture output → validate → score → clean up
6. **Result aggregation** — write `ResultMatrix`, compute decisions, update the SQLite trend index

## Matrix Expansion

A `RunPlan` is the Cartesian product of every task, every configuration, and every repetition index:

```
RunCells = Tasks × Configurations × range(repetitions)
```

For example, three tasks, two configurations, and two repetitions yields **12 cells**:

```yaml{4,8,11}
tasks:
  - id: refactor
  - id: add-tests
  - id: fix-bug

configurations:
  - id: sonnet-skill-v1
  - id: sonnet-skill-v2

# repetitions is set per configuration:
# configurations[].repetitions: 2
```

Each cell carries a stable identity — `(task_id, config_id, rep_index)` — recorded in `plan.json` before execution begins. This means partial results from an interrupted run are always traceable.

## Execution Order

By default, cells execute in **deterministic order**: tasks iterate in declaration order, then configurations, then repetitions. This makes consecutive runs directly comparable.

When you need to eliminate ordering effects — for example, suspecting that sequential workspace writes influence later cells — enable randomization:

```yaml{2}
guardrails:
  randomize_execution_order: true
  # execution_seed is auto-generated and recorded in plan.json
```

The generated `execution_seed` is always written to `plan.json` and embedded in `RunResult.metadata`, so the exact order can be replayed.

## Concurrency Control

Cells run concurrently via `asyncio`, with a bounded semaphore:

```yaml
guardrails:
  max_concurrency: 4    # default; adjust based on available CPU/memory
```

::: tip Tuning `max_concurrency`
For CPU-bound agent workloads, set `max_concurrency` to the number of available cores. For API-bound agents (LLM calls), higher values (8–16) are safe. Watch memory — each cell may clone a git worktree and spawn a subprocess.
:::

The semaphore ensures at most `max_concurrency` cells are in their subprocess phase simultaneously. Workspace preparation and cleanup happen outside the semaphore to avoid blocking other cells.

## Per-Cell Lifecycle

Every `RunCell` passes through the same eight-step lifecycle. A failure at any step produces a structured `CellError` and skips remaining steps for that cell — but does not affect other cells.

### Step 1 — Workspace Preparation

The engine provisions an isolated workspace for each cell based on `workspace.type`:

| Type | What happens |
|---|---|
| `blank` | Creates an empty temporary directory |
| `files` | Copies declared files into a temp directory |
| `git_repo` | Creates a `git worktree` from the specified repo and commit |

```yaml
workspace:
  type: git_repo
  path: .
  ref: HEAD           # pinned for reproducibility
  setup:
    - ["uv", "sync"]
```

The worktree path is unique per cell — parallel cells never share a filesystem root.

### Step 2 — Setup Commands

`setup` commands run sequentially inside the workspace before the agent is invoked. Every command must be an **argv list** (no shell strings):

```yaml{3,4,5}
workspace:
  setup:
    - ["uv", "sync", "--frozen"]
    - ["npm", "ci"]
    - ["python", "scripts/seed_db.py"]
```

If any setup command exits with a non-zero code, the cell immediately transitions to `error` state with `phase: setup`. The agent is not invoked.

### Step 3 — Agent Subprocess Invocation

The agent is launched via Python's `asyncio.create_subprocess_exec` — **never** via `shell=True`. The full command is constructed as an argv list:

```yaml
configurations:
  - id: my-agent
    agent:
      command: ["uv", "run", "my-agent"]
      args: ["--task-file", "{task_file}"]   # placeholder expanded safely
      timeout: 120
```

The task prompt is delivered via a temporary file or stdin — never interpolated into a shell string. This eliminates an entire class of injection vulnerabilities.

::: warning argv-only security
micro-eval refuses to execute agent commands passed as shell strings. If your `command` value is a single string containing spaces or shell metacharacters, the CLI will reject the configuration at validate time with a clear error. Always use lists: `["my-agent", "--flag", "value"]`.
:::

### Step 4 — Output Capture

stdout, stderr, and declared artifact paths are captured with size caps to prevent runaway output from exhausting disk:

```yaml
guardrails:
  output_cap_bytes: 10485760    # 10 MB per cell (default)
  artifact_cap_bytes: 52428800  # 50 MB per artifact (default)
```

When a stream exceeds its cap, capture stops and `stdout_truncated: true` (or `stderr_truncated: true`) is set on the `CellResult`. The agent process is not killed — only the capture buffer is capped.

::: warning Truncated output affects validation
If `stdout_truncated` is `true`, `contains` expectations that match against the end of stdout may produce false negatives. Check `cell_result.stdout_truncated` when debugging unexpected validation failures. Increase `output_cap_bytes` in `guardrails` if your agent produces large structured output.
:::

### Step 5 — Deterministic Validation

Expectations are evaluated against captured output in declaration order. micro-eval supports four expectation types:

::: code-group

```yaml [exit_code]
expectations:
  - type: exit_code
    value: 0
```

```yaml [contains]
expectations:
  - type: contains
    stream: stdout
    value: "refactoring complete"
    case_sensitive: false
```

```yaml [file_exists]
expectations:
  - type: file_exists
    path: "output/report.md"
    min_bytes: 100
```

```yaml [command]
expectations:
  - type: command
    command: ["python", "-m", "pytest", "tests/", "-q"]
    cwd: "{output_dir}"
```

:::

All expectations are evaluated even if earlier ones fail — you get a complete picture per cell, not just the first failure.

### Step 6 — Trace Capture (Optional)

If Langfuse credentials are configured, the engine attaches trace metadata to the `CellResult`:

```bash
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...   # stored as LANGFUSE_SECRET_KEY in practice
export LANGFUSE_HOST=https://cloud.langfuse.com
```

Trace capture is best-effort — if the Langfuse endpoint is unreachable, the cell result is still written without trace data.

### Step 7 — Optional LLM Judge

After deterministic validation, an optional LLM judge scores the cell against a rubric:

```yaml
scoring:
  judge: gpt-4o
  rubric: |
    Score the agent's output on correctness (0-10) and clarity (0-10).
    Return JSON: {"correctness": <int>, "clarity": <int>}
  dimensions: [correctness, clarity]
```

LLM judge failures (API error, malformed JSON response) produce a `judge_error` field on `CellResult` and do not affect the deterministic validation result.

### Step 8 — Workspace Cleanup

After output capture and scoring complete, the workspace is removed:

- `blank` / `files` workspaces: the temp directory is deleted
- `git_repo` workspaces: `git worktree remove --force <path>` is called

Cleanup runs even if the agent exited with an error. Artifacts declared under `run.preserve_artifacts` are copied to `.micro-eval/runs/<run-id>/artifacts/` before the workspace is removed.

## Timeout and Signal Escalation

Each cell has a configurable timeout. When the agent exceeds it, the engine escalates signals:

```
timeout exceeded
  → SIGTERM (graceful shutdown)
  → grace_window seconds (default: 10)
  → SIGKILL (forced)
```

Configure per configuration or globally:

```yaml{4,5}
configurations:
  - id: slow-agent
    agent:
      timeout: 300          # seconds; overrides run-level default
      grace_window: 15      # seconds between SIGTERM and SIGKILL
```

The `CellResult` records `exit_reason: timeout` and the actual wall-clock duration.

## Cell Failure Isolation

By default, a cell error (setup failure, agent crash, timeout) is recorded as a `CellResult` with `status: error` and the run continues:

```yaml
guardrails:
  stop_on_cell_error: false   # default — continue on error
```

Set `stop_on_cell_error: true` if you want the entire run to halt on the first failure. This is useful during initial configuration to surface problems quickly.

::: tip Partial results are always written
Even when a run is interrupted (Ctrl-C, OOM, network drop), every completed cell's result is flushed to disk as it finishes. You will never lose results from cells that completed before the interruption.
:::

## Isolation Levels

The workspace provider determines how cells are isolated from each other and from the host:

| Level | Provider | Guarantee |
|---|---|---|
| `logical` | git worktree | Separate filesystem tree; shares host OS resources |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | Syscall/filesystem policy enforced by the OS |
| `container` | Docker (planned) | Full container namespace isolation |
| `vm` | E2B / Modal | Remote ephemeral VM; strongest isolation |

```yaml{3}
workspace:
  isolation_level: os_policy    # falls back to logical with a caveat if unavailable
```

When `os_policy` is requested but Seatbelt/Bubblewrap is unavailable (e.g., wrong OS or missing permissions), micro-eval downgrades to `logical` and records a `SandboxCaveat` in the run metadata. Remote providers (`E2B`, `Modal`) **never downgrade** — they fail hard if credentials are absent.

## Guardrails Reference

All safety limits live under `guardrails`:

```yaml
guardrails:
  max_concurrency: 4
  output_cap_bytes: 10485760
  artifact_cap_bytes: 52428800
  randomize_execution_order: false
  stop_on_cell_error: false
```

## Secrets Handling

Environment variables prefixed with `MICRO_EVAL_SECRET_` are forwarded to agent subprocesses but **automatically redacted** from all logs, traces, and stored `CellResult` records:

```bash
export MICRO_EVAL_SECRET_OPENAI_API_KEY=sk-...
export MICRO_EVAL_SECRET_GITHUB_TOKEN=ghp_...
```

Do not pass secrets via `args` in the configuration YAML — those values are stored in `plan.json` and are not redacted.

::: danger Never put secrets in YAML
Anything written to `eval.yaml` or any field under `configurations[].agent.args` ends up in `.micro-eval/runs/<run-id>/plan.json` in plaintext. Use `MICRO_EVAL_SECRET_*` env vars for all credentials.
:::

## Next Steps

With execution covered, the next topic explains how micro-eval scores and annotates results:

[Evaluation →](/guide/evaluation)
