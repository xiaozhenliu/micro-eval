# Tasks & Expectations

A **task** is the fundamental unit of evaluation in micro-eval. Each task describes a single scenario: the input given to the agent, the environment the agent runs in, and the rules for judging whether the agent succeeded.

Tasks are defined in YAML files and referenced by a `Run`. During a run, micro-eval expands `Tasks × Configurations × Repetitions` into a result matrix, executing each task against every configuration the number of times specified by `repetitions`.

## Complete Task Structure

```yaml
# tasks/refactor-extract-function.yaml
id: refactor-extract-function
name: "Extract helper function from monolith"
description: >
  Given a 200-line Python file, the agent should extract a
  clearly reusable helper into a separate function with a
  descriptive name and update all call sites.

input_payload: |
  Refactor the code in src/utils.py. Extract the date-parsing
  logic (lines 45-72) into a standalone function called
  `parse_iso_date`. Update every call site in the same file.

expected_output: |
  def parse_iso_date(value: str) -> datetime:
      ...

rubric:
  text: "Did the agent correctly extract the function without breaking existing behavior?"
  dimensions:
    - name: correctness
      weight: 0.5
      description: "All tests pass after the refactor"
    - name: naming
      weight: 0.2
      description: "Function name matches the specification"
    - name: call_sites
      weight: 0.3
      description: "Every call site in utils.py is updated"

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "def parse_iso_date"
    stream: stdout
  - type: file_exists
    path: "{output_dir}/src/utils.py"
  - type: command
    command: ["python", "-m", "pytest", "tests/", "-q"]
    cwd: "{output_dir}"

workspace:
  type: git_repo
  path: /path/to/your/project
  ref: main
  isolation_level: logical
  trust_level: semi_trusted
  network_policy: none
  setup:
    - ["pip", "install", "-e", "."]
  fixtures:
    - path: testdata/utils_original.py
      digest: sha256:abc123...
  toolchain:
    runtime: python3
    lockfile: requirements.txt

business_impact_tier: 2
tags: [refactor, python, extract-function]
revision_id: "2026-06-15-v1"
```

### Field Reference

| Field | Required | Description |
|---|---|---|
| `id` | yes | Path-safe identifier. Allowed chars: `A-Za-z0-9_.:–`. Must be unique within a project. |
| `name` | yes | Human-readable display name shown in the UI and reports. |
| `description` | no | Longer context about what the task is testing. Shown in run detail pages. |
| `input_payload` | yes | The text or prompt delivered to the agent as its task input. |
| `expected_output` | no | Optional reference answer. Used by the LLM judge as a gold standard when scoring. |
| `rubric` | no | Scoring criteria. Can be a plain string or a structured object with named dimensions and weights. |
| `expectations` | no | Deterministic validation rules run before the LLM judge. Failures short-circuit scoring. |
| `workspace` | no | Execution environment spec. Defaults to `type: blank` with `isolation_level: logical`. |
| `business_impact_tier` | no | `1`–`3` (integer). Surfaced in reports for prioritisation. `1` is highest priority. |
| `tags` | no | Free-form list. Used for filtering with `micro-eval list` and `--tag`. |
| `revision_id` | no | Opaque string for tracking task definition changes over time. |

## The Four Expectation Types

Expectations are **deterministic** checks that run immediately after the agent process exits, before any LLM judge is invoked. They are fast, cheap, and reproducible. Think of them as your first line of defense against obvious failures.

If any expectation fails, the result is marked `failed` and the LLM judge is skipped for that cell in the result matrix.

### `exit_code` — Process exit status

The agent process must exit with the specified numeric code.

```yaml
expectations:
  - type: exit_code
    value: 0
```

Use `value: 0` for tasks where the agent is expected to complete successfully. Use a non-zero value if you are specifically testing error-handling scenarios.

::: tip
`exit_code: 0` should be present in almost every task. It catches crashes, timeouts, and subprocess errors before wasting LLM judge budget.
:::

### `contains` — Output string match

The specified stream must contain the given string. Matching is case-sensitive and literal (no regex).

```yaml
expectations:
  - type: contains
    value: "Task completed successfully"
    stream: stdout

  - type: contains
    value: "parse_iso_date"
    stream: stdout

  - type: contains
    value: "ERROR"
    stream: stderr
```

**`stream` options:**

| Value | Checks |
|---|---|
| `stdout` | Standard output of the agent process |
| `stderr` | Standard error of the agent process |
| `output` | Combined stdout + stderr (default if omitted) |

::: tip
Use `stream: stdout` rather than `output` when you want to assert that the agent produced specific content without noise from log lines on stderr.
:::

### `file_exists` — Output file presence

A file at the given path must exist after the agent finishes. Use `{output_dir}` as a placeholder for the task's workspace directory — micro-eval substitutes the actual path at runtime.

```yaml
expectations:
  - type: file_exists
    path: "{output_dir}/report.md"

  - type: file_exists
    path: "{output_dir}/src/utils.py"

  - type: file_exists
    path: "{output_dir}/dist/bundle.js"
```

::: warning
The agent's working directory is the workspace root, which is the same path that `{output_dir}` resolves to. Do not write paths relative to the project root — the agent does not run in your project directory.
:::

### `command` — External validation script

Run an arbitrary command as a validator. The command must exit with code `0` for the expectation to pass. This is the most powerful expectation type: it lets you run your existing test suite, a linter, a diff check, or any other validation logic.

```yaml
expectations:
  - type: command
    command: ["python", "-m", "pytest", "tests/", "-q", "--tb=short"]
    cwd: "{output_dir}"

  - type: command
    command: ["npx", "tsc", "--noEmit"]
    cwd: "{output_dir}"

  - type: command
    command: ["git", "diff", "--exit-code"]
    cwd: "{output_dir}"

  - type: command
    command: ["bash", "scripts/validate_output.sh"]
    cwd: "{output_dir}"
```

**Important constraints on `command` expectations:**

- `command` must be a list — never a shell string. micro-eval passes arguments directly to the subprocess without a shell, which prevents injection attacks and quoting surprises.
- `cwd` defaults to `{output_dir}` if omitted.
- Stdout and stderr from the command are captured and attached to the run result for debugging, but they do not affect the pass/fail determination — only the exit code matters.

::: warning
Do not use `command: ["sh", "-c", "some command string"]`. If you need shell features, write a script file, commit it to your fixture, and invoke it with `command: ["bash", "scripts/my-check.sh"]`.
:::

## Workspace Types

The `workspace` block controls what environment the agent runs in. Every workspace is isolated: each `(task, configuration, repetition)` cell in the result matrix gets its own independent directory.

### `blank` — Empty directory

The agent starts in an empty temporary directory. Use this for tasks where the agent is expected to create everything from scratch.

```yaml
workspace:
  type: blank
  isolation_level: logical
```

### `files` — Copy specific files

micro-eval copies a set of files or directories into the workspace before the agent runs. The agent sees a clean copy; any mutations it makes do not affect your source files.

```yaml
workspace:
  type: files
  path: testdata/my-scenario/
  isolation_level: logical
  setup:
    - ["npm", "install"]
```

The `path` points to a directory in your project. Its contents are copied recursively into the workspace root.

### `git_repo` — Isolated worktree

micro-eval creates a git worktree from the specified repository at the given ref. This is the most reproducible workspace type: the exact commit is recorded in the run result, making it possible to reproduce any result precisely.

```yaml{3-5}
workspace:
  type: git_repo
  path: /path/to/repo
  ref: main
  isolation_level: logical
  network_policy: none
  setup:
    - ["pip", "install", "-e", ".[dev]"]
  fixtures:
    - path: testdata/seed_data.sql
      digest: sha256:deadbeef...
  toolchain:
    runtime: python3
    lockfile: requirements.txt
```

::: tip
`ref` can be a branch name, a tag, or a full commit SHA. Using a full SHA gives maximum reproducibility and is recommended for regression baselines.
:::

## Isolation Levels

The `isolation_level` field controls how strongly the workspace is sandboxed from the rest of your system.

| Level | Mechanism | Use when |
|---|---|---|
| `logical` | git worktree — filesystem isolation only | Day-to-day development, trusted agents |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) — syscall restrictions | You want OS-level containment without a container runtime |
| `container` | OCI container | You have Docker/Podman available and need full isolation |
| `vm` | E2B or Modal remote VM | Maximum isolation; runs outside your machine entirely |

::: tip
`logical` is the default and requires no additional tooling. Upgrade to `os_policy` when you start evaluating agents that make filesystem or network calls you want to restrict.
:::

::: warning
`container` and `vm` levels require external credentials (`MICRO_EVAL_SECRET_E2B_API_KEY`, `MICRO_EVAL_SECRET_MODAL_TOKEN_ID`, etc.). If the required credentials are absent, micro-eval will error immediately — it does not silently downgrade to a weaker isolation level for these two levels.
:::

## Setup Commands

The optional `setup` block runs a sequence of commands in the workspace before the agent process starts. Each entry is an `argv` list.

```yaml
workspace:
  type: git_repo
  path: /path/to/repo
  ref: main
  setup:
    - ["pip", "install", "-e", ".[dev]"]
    - ["npm", "install", "--prefix", "frontend"]
    - ["python", "scripts/seed_db.py"]
```

Setup commands run in order, and execution stops if any command exits non-zero. Their output is captured and included in the run result under `setup_log`.

::: warning
Setup commands run inside the workspace, not in your project root. The working directory for each setup command is the workspace root. If your setup script references files relative to the project root, copy those files in via `fixtures` or use absolute paths.
:::

## Fixtures

Fixtures let you inject specific file versions into a `git_repo` workspace, overriding what is in the repository at `ref`. Each fixture entry specifies a path (relative to your project) and an optional digest for integrity verification.

```yaml
workspace:
  type: git_repo
  path: /path/to/repo
  ref: main
  fixtures:
    - path: testdata/initial_state.py
      digest: sha256:abc123...
    - path: testdata/config_v2.yaml
      digest: sha256:def456...
```

The `digest` field is optional but recommended. When provided, micro-eval verifies the fixture file matches the digest before the run starts and records it in the `SameStartSnapshot` — the set of dimensions used to determine whether two results are comparable.

## The `{output_dir}` Placeholder

The string `{output_dir}` is substituted at runtime with the absolute path to the workspace directory for the current `(task, configuration, repetition)` cell. It is available in:

- `file_exists` → `path`
- `command` → `cwd`

::: tip
Always use `{output_dir}` instead of hardcoding a path. micro-eval creates a fresh directory per cell, and the actual path includes run-specific components like the run ID and repetition index.
:::

## Rubric Structure

The `rubric` field guides the LLM judge. It can be either a plain string or a structured object.

::: code-group

```yaml [Simple rubric]
rubric: >
  Did the agent produce a working solution that handles edge cases
  and follows the project's naming conventions?
```

```yaml [Structured rubric]
rubric:
  text: "Evaluate the agent's refactoring quality."
  dimensions:
    - name: correctness
      weight: 0.5
      description: "Tests pass; behavior is preserved"
    - name: readability
      weight: 0.3
      description: "Code is clear and follows project style"
    - name: coverage
      weight: 0.2
      description: "All specified locations were updated"
```

:::

Dimension weights must sum to 1.0. The LLM judge uses the rubric text and dimensions to produce a score between 0 and 1 for each dimension, then computes a weighted average.

## Validation → Judge → Human Pipeline

micro-eval evaluates each result in three stages:

1. **Deterministic validation** (`expectations[]`) — runs first, no LLM cost, fast.
2. **LLM judge** — runs only if all expectations pass. Uses `rubric` to score 0–1.
3. **Human annotation** — optional override. A human reviewer can mark a result correct or incorrect in the UI, and that annotation takes precedence over the LLM score in the decision.

The final cell status in the result matrix reflects all three stages. If you need to investigate a surprising result, the run detail page links to the full trace, the agent's stdout/stderr, and any human annotations.
