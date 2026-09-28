# Configuration

::: tip Where you are in the decision loop
A **Configuration** is one column in the result matrix — it defines
*what you are testing*. See [Design System](./design-system#core-objects)
for how configurations relate to the other core objects.
:::

`eval.yaml` is the central configuration file for every micro-eval experiment. It answers one question: **what exactly are you comparing, and under what conditions?** Everything — the agents under test, the tasks to run, the isolation policy, the scoring rules — lives here or references files that do.

## Complete Example

Copy this file as a starting point, then trim the sections you don't need.

```yaml
# eval.yaml
project_name: my-agent-comparison
description: >
  Compare the refactored coding agent (v2) against the baseline (v1)
  on a suite of Python file-transformation tasks.

# ─── Configurations ─────────────────────────────────────────────────────────
# Each configuration is one "column" in the result matrix.
configurations:
  - id: baseline
    name: Agent v1 (baseline)
    role: baseline          # baseline | candidate
    repetitions: 3          # how many times each task is run

    agent:
      command: ["python", "-m", "myagent.cli", "--mode", "transform"]
      input_mode: stdin     # stdin | file
      output_mode: stdout   # stdout | file | directory
      timeout_s: 120
      env:
        LOG_LEVEL: warning
      required_secrets:
        - MICRO_EVAL_SECRET_OPENAI_KEY

    skills_profile: null    # path to a skills YAML, or null

    parameters:             # arbitrary key-value passed as --param k=v
      model: gpt-4o-mini
      temperature: "0.0"

  - id: candidate
    name: Agent v2 (candidate)
    role: candidate
    repetitions: 3

    agent:
      command: ["python", "-m", "myagent_v2.cli", "--mode", "transform"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 120
      env:
        LOG_LEVEL: warning
      required_secrets:
        - MICRO_EVAL_SECRET_OPENAI_KEY

    skills_profile: skills/coding-v2.yaml

    parameters:
      model: gpt-4o
      temperature: "0.0"

# ─── Tasks ───────────────────────────────────────────────────────────────────
# Paths to task YAML files (relative to this file).
tasks:
  - tasks/rename-function.yaml
  - tasks/add-docstring.yaml
  - tasks/refactor-class.yaml

# ─── Guardrails ──────────────────────────────────────────────────────────────
guardrails:
  max_concurrency: 4          # parallel cells (default: 4)
  timeout_s: 300              # per-cell wall-clock timeout
  output_cap_bytes: 10485760  # 10 MB stdout cap
  artifact_cap_bytes: 52428800  # 50 MB artifact cap
  stop_on_cell_error: false   # abort entire run on first failure
  randomize_execution_order: false

# ─── Evaluation ──────────────────────────────────────────────────────────────
evaluation:
  comparison_subject: score   # what to compare across configurations
  min_repetitions: 2          # minimum reps needed to compute a decision
  required_evaluators:        # which evaluators must have run
    - validator
  denominator_policy: exclude_failed  # include_failed | exclude_failed
  decision_threshold: 0.10    # delta below which result is "inconclusive"
  inconclusive_policy: warn

# ─── Trace ───────────────────────────────────────────────────────────────────
trace:
  enabled: false
  provider: process           # process | langfuse

# ─── LLM Judge ───────────────────────────────────────────────────────────────
judge:
  enabled: false
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

::: tip Validate before running
Run `micro-eval validate` after editing `eval.yaml` to catch schema errors, missing task files, and unreferenced secrets before spending compute on a full run.
:::

---

## Section Reference

### `project_name` and `description`

```yaml
project_name: my-agent-comparison
description: >
  A multiline description of what this experiment is testing.
```

`project_name` appears in reports and the web UI run list. It does not need to be unique across runs — micro-eval uses auto-generated run IDs for that.

---

### `configurations[]`

Each entry is one column in the result matrix. You need at least one configuration; two or more are required for comparison decisions.

#### `id` and `name`

```yaml{2-3}
configurations:
  - id: baseline          # used in the result matrix and file paths
    name: Agent v1 (baseline)  # human-readable label in reports and UI
```

`id` must be unique within the file and contain only alphanumeric characters, hyphens, and underscores.

#### `role`

```yaml{2}
configurations:
  - role: baseline    # baseline | candidate
```

| Value | Meaning |
|---|---|
| `baseline` | The reference. Decisions like `improved`/`regressed` are relative to this. |
| `candidate` | The variant being tested. |

A single configuration can run without a role, but automatic comparison requires exactly one explicit `baseline` and one explicit `candidate`. Missing or ambiguous roles produce `inconclusive`; list order never assigns roles.

#### `repetitions`

```yaml{2}
configurations:
  - repetitions: 3
```

Each task is executed this many times for this configuration. The result matrix records repetitions, pass rates, pass@k/pass^k, and timing statistics; it does not compute a p-value. Set to `1` for deterministic tasks; `3–5` for LLM-driven agents where variance matters.

#### `agent`

An **AgentSpec** is the complete invocation contract for one agent. It tells micro-eval the command argv, how input is delivered to the agent, how output is collected, a per-invocation timeout, extra environment variables, and which secrets are required. Every configuration embeds exactly one AgentSpec under the `agent` key.

```yaml
agent:
  command: ["python", "-m", "myagent.cli", "--mode", "transform"]
  input_mode: stdin
  output_mode: stdout
  timeout_s: 120
  env:
    LOG_LEVEL: warning
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

::: warning command must be an argv list, not a shell string
`command` must be a YAML list — one element per argument. Never write:

```yaml
# WRONG — shell injection risk, will not work as expected
command: "python -m myagent.cli --mode transform"
```

Write it as a list:

```yaml
# CORRECT
command: ["python", "-m", "myagent.cli", "--mode", "transform"]
```

micro-eval passes the list directly to the subprocess, bypassing the shell entirely. This prevents shell injection and ensures argument boundaries are exact.
:::

**`input_mode`**

| Value | Behaviour |
|---|---|
| `stdin` | Task prompt is written to the agent's standard input. |
| `file` | Task prompt is written to a temp file; its path is appended as the final argv element. |

**`output_mode`**

| Value | Behaviour |
|---|---|
| `stdout` | Agent output is captured from standard output. |
| `file` | Agent writes to a path it receives; micro-eval reads that path after exit. |
| `directory` | Agent writes one or more files to a directory; micro-eval collects all of them as artifacts. |

**`timeout_s`**

Per-invocation wall-clock timeout in seconds. The cell is marked `timeout` if exceeded. This value is also bounded by `guardrails.timeout_s` — the lower of the two applies.

**`env`**

Key-value pairs merged into the subprocess environment. These are plaintext values. For secrets, use `required_secrets` instead.

**`required_secrets`**

```yaml
required_secrets:
  - MICRO_EVAL_SECRET_OPENAI_KEY
  - MICRO_EVAL_SECRET_ANTHROPIC_KEY
```

Names of environment variables that must be present at run time and will be forwarded to the subprocess. micro-eval validates they exist before launching any cell and redacts their values from logs and stored traces. Secret variables must follow the naming convention `MICRO_EVAL_SECRET_*` or be listed here explicitly so the redactor knows to scrub them.

#### `skills_profile`

```yaml
skills_profile: skills/coding-v2.yaml  # or null
```

Path to a skills YAML file mounted into the agent's workspace. Use `null` when the agent does not use a skills profile. The path is resolved relative to `eval.yaml`.

#### `parameters`

```yaml
parameters:
  model: gpt-4o
  temperature: "0.0"
  max_tokens: "4096"
```

Arbitrary string key-value pairs passed to the agent as `--param key=value` argv elements appended after `command`. All values must be strings (quote numbers). Parameters appear in the result matrix column headers and are stored with each run for reproducibility.

---

### `tasks[]`

```yaml
tasks:
  - tasks/rename-function.yaml
  - tasks/add-docstring.yaml
```

A list of paths to task YAML files, resolved relative to `eval.yaml`. Each task becomes one row in the result matrix. See the [Tasks](/guide/tasks) guide for the task file format.

---

### `guardrails`

Guardrails cap resource usage and control execution behaviour at the run level.

```yaml
guardrails:
  max_concurrency: 4
  timeout_s: 300
  output_cap_bytes: 10485760
  artifact_cap_bytes: 52428800
  stop_on_cell_error: false
  randomize_execution_order: false
```

| Field | Default | Description |
|---|---|---|
| `max_concurrency` | `4` | Maximum number of cells (task × configuration × repetition) executing in parallel. |
| `timeout_s` | `300` | Recorded guardrail value; current execution uses `agent.timeout_s` and does not apply this as a global override. |
| `output_cap_bytes` | `10485760` | Maximum bytes retained per stdout/stderr stream and selected output (10 MiB). Excess output is marked truncated. |
| `artifact_cap_bytes` | `52428800` | Artifact persistence cap (50 MiB). Output-mode and provider-transfer limits may be lower. |
| `stop_on_cell_error` | `false` | Recorded policy intent. Current dispatch continues after cell errors; this flag does not stop the run. |
| `randomize_execution_order` | `false` | Shuffle cell execution order to reduce systematic ordering bias. |

::: tip Tuning concurrency
`max_concurrency` controls how many agent subprocesses run at once across all configurations and repetitions. Start low (2–4) when agents make external API calls with rate limits, or when you are measuring latency and want to avoid contention.
:::

---

### `evaluation`

Records the comparison contract. Automatic decisions compare task-level validator pass rates; roles and this contract are preserved with the run.

```yaml
evaluation:
  comparison_subject: score
  min_repetitions: 2
  required_evaluators:
    - validator
  denominator_policy: exclude_failed
  decision_threshold: 0.10
  inconclusive_policy: warn
```

| Field | Default | Description |
|---|---|---|
| `comparison_subject` | `null` | Human-readable description of the comparison, not a metric selector. |
| `min_repetitions` | `1` | Minimum denominator samples on both sides of every task. An unmet count makes the decision `inconclusive`. |
| `required_evaluators` | `["validator"]` | Required evaluation contract. Automatic comparisons currently support only `["validator"]`; other contracts require human review. |
| `denominator_policy` | `include_failed` | `include_failed` counts errors/timeouts; `exclude_failed` keeps passed/failed results and excludes execution failures. |
| `decision_threshold` | `null` | Task-level candidate-minus-baseline pass-rate threshold in `(0, 1]`. `null` disables automatic winner decisions. |
| `inconclusive_policy` | `warn` | Recorded policy intent: `warn` or `block`. It does not select or override the guarded report verdict. |

**`denominator_policy`**

::: code-group

```yaml [exclude_failed]
# Count passed and failed results; exclude execution errors and timeouts.
# Failed expectations still count.
denominator_policy: exclude_failed
```

```yaml [include_failed]
# All cells (including timeouts and errors) count toward the denominator.
# Use when failure rate itself is part of what you are measuring.
denominator_policy: include_failed
```

:::

**Decision statuses**

| Status | Meaning |
|---|---|
| `improved` | At least one task reaches the improvement threshold and none regress. |
| `regressed` | At least one task reaches the regression threshold and none improve. |
| `mixed` | Different tasks show opposite directions. |
| `inconclusive` | No task reaches a threshold, or roles, contract, samples, or machine evidence are insufficient. |
| `not_comparable` | A cell snapshot gate warns/fails or the compared task sets differ. |
| `needs_human_review` | The contract requires non-validator evaluation. |

---

### `trace`

```yaml
trace:
  enabled: false
  provider: process   # process | langfuse
```

When `enabled: true` with `provider: process`, micro-eval captures timing and token-usage data from the subprocess using its own lightweight tracer. Switch to `provider: langfuse` to forward spans to a running Langfuse instance — set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` in your environment. Tracing is always optional; runs proceed normally if the provider is unavailable.

---

### `judge`

```yaml
judge:
  enabled: false
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

The LLM judge runs after the deterministic validator and produces a continuous score between 0 and 1. It is optional — disable it when deterministic expectations are sufficient, or when you want to keep costs down during initial iteration.

| Field | Description |
|---|---|
| `provider` | Scoring backend. Currently `deepeval`. |
| `model` | Model ID passed to the provider for judging. |
| `temperature` | Sampling temperature for the judge model. `0.0` gives deterministic judgements. |
| `pass_threshold` | Minimum score to consider a cell "passing" for aggregation purposes. |
| `required_secrets` | Secrets forwarded to the judge provider (not to the agent). |

::: warning Judge costs are separate from agent costs
The judge model makes its own API calls. On large task suites with many repetitions, judge costs can exceed agent costs. Budget accordingly, or set `judge.enabled: false` and rely on `required_evaluators: [validator]` until you need LLM-based scoring.
:::

---

## Config Lookup Order

micro-eval resolves `eval.yaml` using the following precedence (first match wins):

1. **`--config <path>`** flag passed to `micro-eval run` or `micro-eval validate`
2. **`$MICRO_EVAL_CONFIG`** environment variable
3. **`./eval.yaml`** in the current working directory

::: code-group

```bash [flag]
micro-eval run --config experiments/my-experiment.yaml
```

```bash [env var]
export MICRO_EVAL_CONFIG=experiments/my-experiment.yaml
micro-eval run
```

```bash [default]
# eval.yaml in current directory is used automatically
micro-eval run
```

:::

---

## Minimal Configuration

Not every section is required. Here is the smallest valid `eval.yaml`:

```yaml
project_name: hello-eval

configurations:
  - id: my-agent
    agent:
      command: ["python", "agent.py"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 60

tasks:
  - tasks/hello.yaml
```

Omitted sections use their defaults: 1 repetition, max_concurrency 4, no judge, no trace, exclude_failed denominator.

---

## Next Steps

- [Tasks](/guide/tasks) — define the rows of your result matrix: prompts, workspaces, and expectations.
