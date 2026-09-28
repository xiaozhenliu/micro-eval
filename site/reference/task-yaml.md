# task.yaml Schema

A **task** is the atomic unit of evaluation in micro-eval. Every task describes one prompt, its expected outcomes, and the workspace that must exist when the agent runs. Tasks are stored as YAML files and loaded at run-time by the engine.

::: tip Quick start
Run `micro-eval init` to generate a starter `task.yaml` in your project, then extend it using the field reference below.
:::

## File structure overview

```yaml
# task.yaml
id: summarize-pr-diff
name: Summarize a pull-request diff
description: Agent must produce a concise summary of a git diff.

input_payload: |
  Summarize the following git diff in 3 bullet points.
  Focus on what changed and why it matters.
  {{diff}}

expected_output: "- "
rubric:
  text: Evaluate the summary for accuracy, brevity, and actionability.
  dimensions:
    - accuracy
    - brevity
    - { name: actionability, weight: 0.5 }

workspace:
  type: git_repo
  path: ./fixtures/sample-repo
  ref: HEAD
  isolation_level: logical

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "- "
    stream: output

business_impact_tier: 2
tags: [code-review, summarization]
revision_id: v1
```

---

## TaskSpec

The root object of a `task.yaml` file.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | `string` | yes | — | Unique task identifier. Only `A-Za-z0-9_.:‑` characters allowed. Used in file paths and result keys. |
| `name` | `string` | yes | — | Human-readable display name shown in the UI and reports. |
| `description` | `string` | no | `""` | Optional longer description. Shown in run summaries. |
| `input_payload` | `string` | yes | — | The prompt text delivered to the agent via stdin or file. Supports `{{variable}}` placeholders resolved at run-time. |
| `expected_output` | `string \| null` | no | `null` | Reference string used by deterministic validators and as context for LLM judge scoring. |
| `rubric` | `string \| RubricSpec \| null` | no | `null` | Scoring criteria. A plain string is treated as `rubric.text`. |
| `expectations` | `ExpectationSpec[]` | no | `[]` | Ordered list of deterministic checks applied after the agent exits. All must pass for the task to be marked `passed`. |
| `workspace` | `WorkspaceSpec` | no | `{type: blank}` | Describes the filesystem environment and isolation policy for agent execution. |
| `business_impact_tier` | `int` | no | `3` | Priority tier (`1` = highest). Used to weight aggregate scores in the ResultMatrix. |
| `tags` | `string[]` | no | `[]` | Arbitrary labels for filtering runs (`micro-eval run --tag code-review`). |
| `revision_id` | `string` | no | `""` | Tracks the version of this task definition. Stored in run results for comparability checks. |
| `scenario` | `string \| null` | no | `null` | Conversational evaluation only: describes the scenario the simulated user acts out across multiple turns. |
| `expected_outcome` | `string \| null` | no | `null` | Conversational evaluation only: the outcome the conversation should reach by its end. |
| `user_description` | `string \| null` | no | `null` | Conversational evaluation only: describes the simulated user's persona and goals. |

::: tip Conversational evaluation fields
`scenario`, `expected_outcome`, and `user_description` are optional and only used for multi-turn conversational evaluation. When all three are empty, the task runs through the standard single-turn path. Set `scenario` (and typically the other two) to opt a task into multi-turn simulation — see [Conversational evaluation](/guide/conversational-evaluation).
:::

::: warning id format
The `id` field must be path-safe. Avoid spaces, slashes, and special characters. A good pattern is `kebab-case` or `snake_case`. The engine uses this value to construct output paths like `.micro-eval/runs/<run-id>/tasks/<task-id>/`.
:::

---

## ExpectationSpec

Expectations are deterministic checks executed after the agent subprocess exits. They run in order.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | `string` | yes | — | One of `exit_code`, `contains`, `file_exists`, `command`. |
| `value` | `string \| int \| null` | no | `null` | Expected value. For `exit_code`: integer. For `contains`: substring string. |
| `path` | `string \| null` | no | `null` | File path relative to the workspace root. Used by `file_exists`. |
| `stream` | `string` | no | `"output"` | Which stream to check for `contains`. One of `stdout`, `stderr`, `output` (stdout + stderr combined). |
| `command` | `string[] \| null` | no | `null` | Argv array for the `command` type. Never use shell strings — pass arguments as a list. |
| `cwd` | `string \| null` | no | `null` | Working directory for `command` execution. Supports `{output_dir}` as a placeholder. |
| `timeout_s` | `float` | no | `30.0` | Seconds before the expectation command is killed. |

### Expectation type: `exit_code`

Checks that the agent process exited with a specific code.

```yaml{3-4}
expectations:
  - type: exit_code
    value: 0          # pass if agent exits cleanly
```

```yaml
expectations:
  - type: exit_code
    value: 1          # expect intentional failure (e.g. a linting task)
```

### Expectation type: `contains`

Checks that a specific substring is present in the agent's output.

```yaml{3-5}
expectations:
  - type: contains
    value: "LGTM"
    stream: output    # stdout + stderr merged
```

```yaml
expectations:
  - type: contains
    value: "ERROR"
    stream: stderr    # only check stderr
```

::: tip Multiple substrings
Add multiple `contains` expectations to assert several strings are all present. Each is checked independently.
:::

### Expectation type: `file_exists`

Checks that the agent created (or preserved) a file at a given path within the workspace.

```yaml{3-4}
expectations:
  - type: file_exists
    path: output/report.md     # relative to workspace root
```

```yaml
expectations:
  - type: file_exists
    path: dist/bundle.js
  - type: file_exists
    path: dist/bundle.css
```

### Expectation type: `command`

Runs an arbitrary command and checks its exit code is `0`. Use this for test runners, linters, or custom validators.

```yaml{3-6}
expectations:
  - type: command
    command: [python, -m, pytest, tests/]
    cwd: "{output_dir}"        # run inside the agent's output directory
    timeout_s: 60.0
```

```yaml
expectations:
  - type: command
    command: [npx, tsc, --noEmit]
    cwd: "{output_dir}"
```

::: danger Never use shell strings in command
Always pass `command` as a YAML list of strings (argv). The engine passes these directly to the subprocess — no shell interpolation occurs. Shell strings create injection risk and break on filenames with spaces.

```yaml
# WRONG — shell string
command: "pytest tests/ && echo done"

# CORRECT — argv list
command: [pytest, tests/]
```
:::

---

## WorkspaceSpec

Describes the filesystem state the agent sees at startup and the isolation policy applied during execution.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `type` | `string` | no | `"blank"` | Workspace type. One of `blank`, `files`, `git_repo`. |
| `path` | `string \| null` | no | `null` | Source repository path. Required when `type: git_repo`. |
| `ref` | `string \| null` | no | `null` | Git ref (branch, tag, or SHA) to check out. Defaults to the current HEAD. |
| `files` | `string[]` | no | `[]` | List of file or directory paths to copy into the workspace. Used with `type: files`. |
| `setup` | `string[][]` | no | `[]` | Argv command lists run **before** the agent starts, inside the workspace. Use to install dependencies or seed data. |
| `isolation_level` | `string` | no | `"logical"` | One of `logical`, `os_policy`, `container`, `vm`. |
| `trust_level` | `string` | no | `"trusted"` | One of `trusted`, `semi_trusted`, `untrusted`, `adversarial`. Informs the sandbox policy. |
| `network_policy` | `string \| null` | no | `null` | One of `full`, `allowlist`, `none`, or `null` (inherit from configuration). |
| `fixtures` | `FixtureSource[]` | no | `[]` | Additional files injected into the workspace with optional digest verification. |
| `toolchain` | `ToolchainSpec \| null` | no | `null` | Runtime and lockfile fingerprint for comparability tracking. |

### Workspace type: `blank`

An empty temporary directory. The agent starts with no pre-existing files.

```yaml
workspace:
  type: blank
  isolation_level: logical
```

Use `blank` for tasks where the agent must create all output from scratch, such as generating a file from a prompt.

### Workspace type: `files`

Copies a set of files or directories into the workspace before the agent runs.

```yaml{2-7}
workspace:
  type: files
  files:
    - ./fixtures/input.csv
    - ./fixtures/schema.json
  setup:
    - [pip, install, -r, requirements.txt]
  isolation_level: logical
```

::: tip Relative paths
Paths in `files` are resolved relative to the `task.yaml` file. Use project-relative paths for reproducibility.
:::

### Workspace type: `git_repo`

Checks out a git repository at a specific ref using a git worktree. This is the recommended type for code-editing and agentic coding tasks.

```yaml{2-6}
workspace:
  type: git_repo
  path: ./fixtures/sample-repo    # path to a git repo on disk
  ref: main                       # branch, tag, or full SHA
  isolation_level: logical        # git worktree per run
```

```yaml
# Pin to an exact commit for maximum reproducibility
workspace:
  type: git_repo
  path: /abs/path/to/repo
  ref: a3f9c12e
  isolation_level: os_policy
```

::: warning git_repo requires a git repository
The path must point to a directory that is itself a git repository (contains a `.git` directory). The engine uses `git worktree add` to create an isolated copy for each run.
:::

### Isolation levels

| Level | Backend | Description |
|---|---|---|
| `logical` | git worktree | Each run gets its own worktree. Fast, no OS-level sandboxing. Default. |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | OS-enforced syscall and filesystem policy. Falls back to `logical` with a caveat if unavailable. |
| `container` | Reserved | Not yet implemented. |
| `vm` | E2B / Modal | Remote VM execution. Requires provider credentials. Fails hard if unconfigured — does not fall back. |

::: code-group

```yaml [Development (logical)]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: logical
```

```yaml [CI (os_policy)]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

```yaml [Remote (vm)]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: vm
  trust_level: untrusted
  network_policy: none
```

:::

### Setup commands

Setup commands run inside the workspace before the agent starts. Pass them as a list of argv lists — never shell strings.

```yaml{4-7}
workspace:
  type: git_repo
  path: ./fixtures/python-project
  setup:
    - [python, -m, pip, install, -r, requirements.txt]
    - [python, scripts/seed_db.py]
  isolation_level: logical
```

---

## FixtureSource

Additional files injected into the workspace alongside the primary workspace type. Supports digest verification to detect fixture drift between runs.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | `string` | yes | — | Path to the fixture file, resolved relative to `task.yaml`. |
| `digest` | `string \| null` | no | `null` | Expected SHA-256 hex digest. If provided, the engine verifies the file before injection and records the digest in the run result for comparability checks. |

```yaml{8-13}
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: logical
  fixtures:
    - path: ./fixtures/data/users.csv
      digest: "e3b0c44298fc1c149afb..."    # SHA-256 of the file
    - path: ./fixtures/data/config.json
      digest: null                           # no verification
```

::: tip Why digest matters
micro-eval uses fixture digests as part of `SameStartSnapshot` comparability checks. Two runs are only considered comparable if their fixture digests match. Without a digest, fixture changes go undetected and can silently invalidate trend analysis.
:::

---

## ToolchainSpec

Records the runtime and lockfile used by the agent's environment. The engine hashes these files and stores the fingerprint in the run result. Trend analysis uses this fingerprint to mark runs as `not_comparable` when the toolchain changes.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `runtime` | `string \| null` | no | `null` | Runtime identifier string, e.g. `python3`, `node`. Informational only. |
| `lockfile` | `string \| null` | no | `null` | Path to a lockfile (e.g. `requirements.txt`, `package-lock.json`). The engine SHA-256 hashes this file and records the fingerprint. |

```yaml{10-12}
workspace:
  type: git_repo
  path: ./fixtures/python-project
  ref: HEAD
  isolation_level: logical
  setup:
    - [pip, install, -r, requirements.txt]
  toolchain:
    runtime: python3
    lockfile: ./fixtures/python-project/requirements.txt
```

---

## RubricSpec

Defines criteria for LLM-judge scoring. A rubric is evaluated only when deterministic expectations pass (or are absent). Human annotation can override the LLM score at any time.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `text` | `string` | yes | — | Natural-language description of what "good" looks like. Sent verbatim to the LLM judge. |
| `dimensions` | `(string \| dict)[]` | no | `[]` | Ordered list of scoring dimensions. Each entry is either a plain string name or a dict with `name` and optional `weight` (float, default `1.0`). |

```yaml
rubric:
  text: |
    Evaluate the agent's response on the following criteria:
    1. Accuracy — does it correctly describe what changed?
    2. Brevity — is it concise without losing meaning?
    3. Actionability — does a reviewer know what to do next?
  dimensions:
    - accuracy
    - brevity
    - { name: actionability, weight: 0.5 }
```

A rubric can also be provided as a plain string shorthand:

```yaml
rubric: "The summary must be accurate, concise, and actionable."
```

::: tip Evaluation pipeline
The engine applies checks in this order:
1. Deterministic `expectations` — fast, no API calls
2. LLM judge using `rubric` — only if `expected_output` or `rubric` is set
3. Human annotation — always available in the UI, overrides LLM score
:::

---

## Complete examples

### Minimal task

```yaml
id: hello-world
name: Hello World

input_payload: |
  Print the text "Hello, World!" and nothing else.

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "Hello, World!"
    stream: output
```

### Code-editing task with git workspace

```yaml
id: add-type-hints
name: Add type hints to Python function

description: |
  Agent must add PEP-484 type annotations to a bare Python function
  and ensure mypy passes with no errors.

input_payload: |
  Add complete type hints to the function in src/utils.py.
  Run `mypy src/utils.py` to verify — it must exit 0.

workspace:
  type: git_repo
  path: ./fixtures/python-project
  ref: add-type-hints-base
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
  toolchain:
    runtime: python3
    lockfile: ./fixtures/python-project/requirements.txt

expectations:
  - type: exit_code
    value: 0
  - type: command
    command: [mypy, src/utils.py, --strict]
    cwd: "{output_dir}"
    timeout_s: 30.0

rubric:
  text: |
    Evaluate whether the type hints are complete, correct, and idiomatic.
    Partial hints that silence mypy by casting to Any are not acceptable.
  dimensions:
    - completeness
    - correctness
    - { name: idiomatic_style, weight: 0.5 }

business_impact_tier: 2
tags: [python, type-safety]
revision_id: v2
```

### File-generation task with fixtures

```yaml
id: generate-report
name: Generate CSV summary report

description: Agent reads raw transaction data and writes a summary CSV.

input_payload: |
  Read the file at input/transactions.csv.
  Write a summary report to output/summary.csv with columns:
  date, total_amount, transaction_count.
  One row per calendar day. Sort ascending by date.

workspace:
  type: files
  files:
    - ./fixtures/transactions.csv
  setup:
    - [mkdir, -p, output]
  isolation_level: logical
  fixtures:
    - path: ./fixtures/transactions.csv
      digest: "abc123def456..."

expected_output: "date,total_amount,transaction_count"

expectations:
  - type: exit_code
    value: 0
  - type: file_exists
    path: output/summary.csv
  - type: contains
    value: "date,total_amount,transaction_count"
    stream: output

business_impact_tier: 3
tags: [data-processing, csv]
```

### Adversarial/untrusted task (remote VM)

```yaml
id: eval-untrusted-agent
name: Run untrusted code in isolated VM

input_payload: |
  Solve the following coding challenge and print the result to stdout.
  {{challenge_text}}

workspace:
  type: blank
  isolation_level: vm
  trust_level: adversarial
  network_policy: none

expectations:
  - type: exit_code
    value: 0

tags: [sandboxed, untrusted]
```

::: warning vm isolation requires credentials
`isolation_level: vm` uses E2B or Modal as the remote provider. If the provider credentials are not configured, the run fails immediately — there is no fallback to a less-isolated level. Set `MICRO_EVAL_SECRET_E2B_API_KEY` or `MICRO_EVAL_SECRET_MODAL_TOKEN` before use.
:::

---

## Field quick-reference

### ExpectationSpec — type values

| `type` | What it checks | Key fields |
|---|---|---|
| `exit_code` | Agent process exit code | `value` (int) |
| `contains` | Substring in agent output | `value` (string), `stream` |
| `file_exists` | File present in workspace | `path` |
| `command` | External command exits 0 | `command` (argv list), `cwd`, `timeout_s` |

### WorkspaceSpec — type values

| `type` | Use case | Required fields |
|---|---|---|
| `blank` | Generation from scratch | none |
| `files` | Static input files | `files` |
| `git_repo` | Code editing, agentic coding | `path` |

### WorkspaceSpec — isolation_level values

| `isolation_level` | Backend | Availability |
|---|---|---|
| `logical` | git worktree | Always available |
| `os_policy` | Seatbelt / Bubblewrap | macOS / Linux; degrades gracefully |
| `container` | Reserved | Not yet implemented |
| `vm` | E2B / Modal | Requires credentials; no fallback |
