# eval.yaml Schema Reference

Every micro-eval project is driven by a single `eval.yaml` file. This file declares what to evaluate (tasks), how to evaluate it (configurations), and under what conditions results are trustworthy (guardrails, evaluation contract).

::: tip File location
By convention, `eval.yaml` lives at the project root alongside your tasks directory. Run `micro-eval init` to generate a commented starter file.
:::

## Minimal example

```yaml
project_name: my-agent-eval
description: Compare v1 vs v2 of my coding agent

configurations:
  - id: v1-baseline
    name: "Agent v1 (baseline)"
    role: baseline
    agent:
      command: ["python", "agent_v1.py"]

  - id: v2-candidate
    name: "Agent v2 (candidate)"
    role: candidate
    agent:
      command: ["python", "agent_v2.py"]

tasks_dir: tasks
```

## Full annotated example

```yaml
project_name: coding-agent-eval
description: "Phase 3 evaluation: tool-use improvements"

configurations:
  - id: gpt4o-baseline
    name: "GPT-4o (baseline)"
    role: baseline
    repetitions: 3
    agent:
      name: coding-agent
      command: ["uv", "run", "agent.py", "--model", "gpt-4o"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 120.0
      env:
        LOG_LEVEL: "info"
      required_secrets:
        - MICRO_EVAL_SECRET_OPENAI_KEY
    parameters:
      temperature: 0.0

  - id: sonnet-candidate
    name: "Claude Sonnet (candidate)"
    role: candidate
    repetitions: 3
    agent:
      name: coding-agent
      command: ["uv", "run", "agent.py", "--model", "claude-sonnet-4-5"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 120.0
      required_secrets:
        - MICRO_EVAL_SECRET_ANTHROPIC_KEY

tasks_dir: tasks
output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 4
  timeout_s: 300.0
  output_cap_bytes: 10485760
  artifact_cap_bytes: 52428800
  stop_on_cell_error: false
  randomize_execution_order: false

evaluation:
  comparison_subject: "tool-use accuracy on file tasks"
  task_set_version: "v1.2"
  success_criteria:
    - "exit code 0 on all tasks"
    - "no regressions vs baseline"
  decision_threshold: 0.05
  inconclusive_policy: warn
  min_repetitions: 3
  required_evaluators:
    - validator
    - judge
  denominator_policy: include_failed

trace:
  enabled: true
  provider: langfuse

judge:
  enabled: true
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

---

## Top-level fields

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `project_name` | `string` | `"unnamed"` | No | Human-readable project label, used in reports and UI. |
| `description` | `string` | `""` | No | Free-text description shown in the run summary and report header. |
| `configurations` | `ConfigurationSpec[]` | — | **Yes** | One or more agent configurations to evaluate. At least one entry required. |
| `tasks` | `string[]` | `[]` | No | Explicit list of task YAML file paths. Takes precedence over `tasks_dir` when both are set. |
| `tasks_dir` | `string` | `"tasks"` | No | Directory scanned for `*.yaml` task files. Ignored when `tasks` is non-empty. |
| `output_dir` | `string` | `".micro-eval/runs"` | No | Where run results are written. Must be a relative path with no `..` segments. |
| `guardrails` | [`Guardrails`](#guardrails) | *(see below)* | No | Resource and safety limits applied to every cell in the run matrix. |
| `evaluation` | [`EvaluationContract`](#evaluationcontract) | *(see below)* | No | How results are compared and what constitutes a decision. |
| `trace` | [`TraceConfig`](#traceconfig) | *(see below)* | No | Observability settings for capturing execution traces. |
| `judge` | [`JudgeConfig`](#judgeconfig) | *(see below)* | No | LLM-as-judge configuration for automatic scoring. |

---

## ConfigurationSpec

A configuration is one column in the result matrix — it fully specifies the agent program, its parameters, and how many times each task should be repeated.

```yaml{4,9-11}
configurations:
  - id: my-agent-v2          # required, path-safe identifier
    name: "My Agent v2"      # required, display name
    role: candidate          # baseline or candidate
    repetitions: 3           # run each task 3 times
    agent:
      command: ["python", "agent.py"]
    parameters:
      temperature: 0.2       # passed to your agent via env or stdin metadata
      max_tokens: 1024
```

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `id` | `string` | — | **Yes** | Unique identifier for this configuration. Allowed characters: `A-Z a-z 0-9 _ . : -`. Used in file paths and report keys. |
| `name` | `string` | — | **Yes** | Display name shown in the UI and reports. |
| `role` | `string \| null` | `null` | No | Declares this configuration as `baseline` or `candidate`. Used by decision logic to compute regression/improvement. |
| `repetitions` | `integer` | `1` | No | Number of times each task is run for this configuration. Minimum: `1`. Higher values reduce variance. |
| `agent` | [`AgentSpec`](#agentspec) | — | **Yes** | The agent program specification. |
| `skills_profile` | `dict` | `{}` | No | Key-value pairs describing which skills or capabilities are mounted for this configuration. Informational — stored in metadata. |
| `parameters` | `dict` | `{}` | No | Arbitrary key-value parameters for this configuration. Stored in run metadata; your agent receives them via stdin task metadata or environment. |

### AgentSpec

Defines the agent executable and how micro-eval communicates with it.

::: warning argv-only execution
`command` is always passed as an argv list to `subprocess` — never interpolated into a shell string. Do not use shell features (pipes, redirects, globs) inside `command`. This is a security requirement, not a convenience limitation.
:::

```yaml
agent:
  name: my-agent
  command: ["uv", "run", "src/agent.py", "--json-output"]
  input_mode: stdin          # or: file
  output_mode: stdout        # or: file, directory
  timeout_s: 120.0
  env:
    LOG_LEVEL: debug
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `name` | `string` | — | No | Human-readable agent name for display purposes. |
| `command` | `string[]` | — | **Yes** | Argv list for launching the agent. Must be non-empty. The first element must be the executable. |
| `input_mode` | `"stdin" \| "file"` | `"stdin"` | No | How the task prompt is delivered. `stdin`: written to the process stdin. `file`: written to a temp file; path passed as the last argv element. |
| `output_mode` | `"stdout" \| "file" \| "directory"` | `"stdout"` | No | Where the agent writes its result. `stdout`: captured from stdout. `file`: agent writes to a known file path. `directory`: agent writes multiple artifacts to a directory. |
| `timeout_s` | `float` | `300.0` | No | Per-cell execution timeout in seconds. Must be greater than `0`. Overrides `guardrails.timeout_s` when set. |
| `env` | `dict` | `{}` | No | Additional environment variables injected into the agent subprocess. Values must be strings. Do not put secrets here — use `required_secrets` instead. |
| `required_secrets` | `string[]` | `[]` | No | Names of secrets this agent needs. Each name must begin with `MICRO_EVAL_SECRET_`. micro-eval reads them from the host environment and injects them into the subprocess; they are never logged or stored in output files. |

#### input_mode in detail

::: code-group

```yaml [stdin (default)]
agent:
  command: ["python", "agent.py"]
  input_mode: stdin
# Task prompt is written to agent's stdin as plain text.
# Agent reads sys.stdin and writes result to stdout.
```

```yaml [file]
agent:
  command: ["python", "agent.py"]
  input_mode: file
# Task prompt is written to a temp file.
# The file path is appended as the last argv element.
# e.g. python agent.py /tmp/micro-eval-task-abc123.txt
```

:::

#### output_mode in detail

::: code-group

```yaml [stdout (default)]
agent:
  output_mode: stdout
# Agent result is captured from stdout.
# Stderr is captured separately for diagnostics but not scored.
```

```yaml [file]
agent:
  output_mode: file
# Agent writes its output to a file path provided via
# the MICRO_EVAL_OUTPUT_FILE environment variable.
```

```yaml [directory]
agent:
  output_mode: directory
# Agent writes multiple artifacts to the directory at
# MICRO_EVAL_OUTPUT_DIR. All files are collected as artifacts.
```

:::

---

## Guardrails

Guardrails cap resource usage and control execution safety for every cell in the `Tasks × Configurations × Repetitions` matrix.

```yaml
guardrails:
  max_concurrency: 4
  timeout_s: 300.0
  output_cap_bytes: 10485760    # 10 MB
  artifact_cap_bytes: 52428800  # 50 MB
  stop_on_cell_error: false
  randomize_execution_order: false
```

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `max_concurrency` | `integer` | `4` | No | Maximum number of cells executing in parallel. Minimum: `1`. Controls asyncio bounded concurrency. |
| `timeout_s` | `float` | `300.0` | No | Default per-cell timeout in seconds. Can be overridden per-agent with `agent.timeout_s`. |
| `output_cap_bytes` | `integer` | `10485760` | No | Maximum bytes captured from stdout/stderr per cell (10 MB). Output beyond this limit is truncated. |
| `artifact_cap_bytes` | `integer` | `52428800` | No | Maximum total bytes of file artifacts collected per cell (50 MB). |
| `stop_on_cell_error` | `boolean` | `false` | No | When `true`, a cell failure (non-zero exit, timeout, error) aborts the entire run immediately. Default `false` collects all results before reporting. |
| `randomize_execution_order` | `boolean` | `false` | No | When `true`, cells are executed in random order. Useful for detecting order-dependent flakiness. |

::: tip Tuning concurrency
Set `max_concurrency` to the number of CPU cores available for local agents, or lower if your agents make external API calls and you want to avoid rate limits.
:::

---

## EvaluationContract

The evaluation contract declares the conditions under which a run produces a trustworthy decision. It is checked after all cells complete.

```yaml{6-8}
evaluation:
  comparison_subject: "file editing accuracy"
  task_set_version: "v2.0"
  success_criteria:
    - "exit code 0 on all tasks"
    - "no regressions vs baseline"
  decision_threshold: 0.05
  inconclusive_policy: warn
  min_repetitions: 3
  required_evaluators:
    - validator
    - judge
  denominator_policy: include_failed
```

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `comparison_subject` | `string \| null` | `null` | No | Human-readable description of what is being compared. Shown in reports. |
| `task_set_version` | `string` | — | No | Version tag for the task set. Stored in run metadata; used to detect non-comparable runs in trend analysis. |
| `success_criteria` | `string[]` | `[]` | No | Human-readable criteria for what constitutes a successful evaluation. Stored as documentation in the run record. |
| `budget` | `dict \| null` | `null` | No | Optional cost budget constraints. Keys and schema depend on your trace provider. |
| `decision_threshold` | `float \| null` | `null` | No | Minimum score delta required to declare a result `improved` or `regressed`. Values below this threshold yield `inconclusive`. |
| `inconclusive_policy` | `"warn" \| "block"` | `"warn"` | No | What happens when the decision is `inconclusive`. `warn` emits a warning and continues. `block` exits with a non-zero status code. |
| `min_repetitions` | `integer` | `1` | No | Minimum repetitions required for a cell to be included in the decision. Cells with fewer successful repetitions are excluded. |
| `required_evaluators` | `string[]` | `["validator"]` | No | Evaluators that must produce a score for a cell to be counted. Supported values: `validator`, `judge`. |
| `denominator_policy` | `"include_failed" \| "exclude_failed"` | `"include_failed"` | No | Whether failed cells (timeout, error) count in the denominator when computing pass rates. `include_failed` is more conservative. |

### Decision statuses

After a run completes, micro-eval computes one of these decision statuses:

| Status | Meaning |
|---|---|
| `improved` | Candidate significantly outperforms baseline (delta ≥ threshold). |
| `regressed` | Candidate significantly underperforms baseline (delta ≤ −threshold). |
| `mixed` | Some tasks improved, some regressed — no clear winner. |
| `inconclusive` | Delta is within the threshold; more data needed. |
| `not_comparable` | Run conditions differ (different task set version, workspace, etc.). |
| `needs_human_review` | Automatic scoring was insufficient; human annotation required. |

---

## TraceConfig

Controls execution tracing for observability. When `provider: langfuse`, configure your Langfuse credentials as `MICRO_EVAL_SECRET_*` environment variables.

```yaml
trace:
  enabled: true
  provider: langfuse   # or: process
```

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `enabled` | `boolean` | `false` | No | Enable trace collection. When `false`, no trace data is emitted. |
| `provider` | `"process" \| "langfuse"` | `"process"` | No | Trace backend. `process`: captures timing and I/O locally. `langfuse`: streams traces to a Langfuse instance (requires `LANGFUSE_*` env vars). |

::: tip Langfuse credentials
Set these in your shell environment before running:
```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com
```
micro-eval reads and injects them automatically; they are never written to output files.
:::

---

## JudgeConfig

Configures an LLM-as-judge for automatic scoring. The judge runs after the deterministic validator and produces a `pass_score` between 0 and 1 for each cell.

::: warning Judge is opt-in
The judge adds latency and cost. Enable it only when deterministic validation (`exit_code`, `contains`, `file_exists`, `command`) is insufficient for your task rubrics.
:::

```yaml
judge:
  enabled: true
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

| Field | Type | Default | Required | Description |
|---|---|---|---|---|
| `enabled` | `boolean` | `false` | No | Enable the LLM judge. When `false`, only deterministic validation runs. |
| `provider` | `"deepeval" \| "deepeval_conversational"` | `"deepeval"` | No | Scoring library to use. `deepeval` runs the single-turn GEval judge described below. `deepeval_conversational` runs multi-turn conversation simulation and scoring instead — see [Conversational evaluation](/guide/conversational-evaluation). |
| `model` | `string` | — | No | Model identifier passed to the judge provider (e.g. `"gpt-4o"`, `"claude-sonnet-4-5"`). |
| `temperature` | `float` | `0.0` | No | Sampling temperature for the judge model. `0.0` is recommended for deterministic scoring. |
| `pass_threshold` | `float` | `0.5` | No | Minimum score (0–1) for the judge to consider a cell passing. Cells below this threshold count as judge-fail. |
| `required_secrets` | `string[]` | `[]` | No | Secrets the judge needs (e.g. the API key for the judge model). Each name must begin with `MICRO_EVAL_SECRET_`. |

### Evaluation pipeline

Evaluation runs in three stages, each building on the previous:

```
┌─────────────────────────────────────────┐
│  Stage 1: Deterministic Validator       │
│  exit_code · contains · file_exists     │
│  command                                │
│  → pass / fail (binary, fast, free)     │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Stage 2: LLM Judge (optional)          │
│  deepeval custom metric                 │
│  → pass_score ∈ [0, 1]                  │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Stage 3: Human Annotation (optional)   │
│  via Web UI annotation interface        │
│  → overrides or supplements judge score │
└─────────────────────────────────────────┘
```

---

## Workspace types

Workspace configuration lives in individual task files, but the isolation level is a property of how micro-eval launches each cell. The four isolation levels are:

| Level | Value | Description |
|---|---|---|
| Logical | `logical` | Git worktree per cell. Fast, no OS-level isolation. Default. |
| OS policy | `os_policy` | Seatbelt (macOS) or Bubblewrap (Linux). Degrades to `logical` with a caveat when unavailable. |
| Container | `container` | OCI container (not local Docker). Planned. |
| VM / Remote | `vm` | E2B or Modal remote sandbox. Requires credentials; fails hard when not configured (no silent degradation). |

The three task workspace types are:

| Type | Description |
|---|---|
| `blank` | Empty directory. Agent starts with no files. |
| `files` | A set of files copied into the workspace before execution. |
| `git_repo` | A git repository checked out at a specific commit. Supports multi-source fixtures and toolchain fingerprinting. |

---

## Secrets handling

::: danger Never put secrets in eval.yaml
Do not write secret values in `eval.yaml`. The file is checked into version control. Use `required_secrets` to declare what secrets are needed, and set them as environment variables before running.
:::

All secret environment variables must use the `MICRO_EVAL_SECRET_` prefix:

```bash
# Set before running micro-eval
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
export MICRO_EVAL_SECRET_ANTHROPIC_KEY=sk-ant-...
export LANGFUSE_SECRET_KEY=sk-lf-...
```

micro-eval:
1. Reads declared secrets from the host environment at startup.
2. Validates that all `required_secrets` are present before launching any cell.
3. Injects them into subprocess environments directly — never via shell interpolation.
4. Auto-redacts all `MICRO_EVAL_SECRET_*` values from stdout, stderr, and artifact captures before writing to disk.

---

## Validation

Run `micro-eval validate` to check your `eval.yaml` against the Pydantic schema before launching a run:

```bash
micro-eval validate
# or point to a specific file:
micro-eval validate --config path/to/eval.yaml
```

Common validation errors:

| Error | Fix |
|---|---|
| `configurations: field required` | Add at least one entry under `configurations`. |
| `id: string does not match pattern` | Configuration `id` must use only `A-Za-z0-9_.:- ` characters. |
| `command: must be non-empty` | `agent.command` must be a list with at least one element. |
| `required_secrets: must use MICRO_EVAL_SECRET_* prefix` | Rename your secret to start with `MICRO_EVAL_SECRET_`. |
| `output_dir: must be relative with no .. segments` | Change `output_dir` to a relative path without `..`. |
| `timeout_s: must be > 0` | Set `timeout_s` to a positive number. |
