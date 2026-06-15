# CLI Commands

Complete reference for all `micro-eval` commands. Current version: **0.3.2**.

## Configuration Lookup Order

Every command that accepts a config file resolves it in this order:

1. `--config PATH` flag (explicit override)
2. `$MICRO_EVAL_CONFIG` environment variable
3. `./eval.yaml` in the current working directory

::: tip
Run all commands from the root of your project so that `./eval.yaml` is found automatically.
:::

---

## micro-eval init

Creates a starter `eval.yaml`, a `tasks/hello.yaml` template, and supporting task scaffolding. Safe to run in an empty directory or an existing project.

**Synopsis**

```
micro-eval init [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--force` | flag | `false` | Overwrite existing `eval.yaml` and task files if they already exist. |

**Generated files**

```
./
├── eval.yaml            # Root configuration (configurations + run settings)
└── tasks/
    └── hello.yaml       # Starter task with one expectation
```

**Examples**

::: code-group

```bash [First time]
# Scaffold a new project
micro-eval init
```

```bash [Re-scaffold]
# Overwrite existing files (useful after an upgrade)
micro-eval init --force
```

:::

**Exit codes**

| Code | Meaning |
|------|---------|
| `0` | Success — files written. |
| `1` | Error — destination exists and `--force` was not passed, or filesystem error. |

---

## micro-eval validate

Loads `eval.yaml` and all referenced task files, resolves the full `RunPlan` (Tasks × Configurations × Repetitions), and prints diagnostics. **No agents are invoked.**

Use this before every `run` to catch schema errors, missing task files, or misconfigured workspace specs early.

**Synopsis**

```
micro-eval validate [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config PATH` | path | _(lookup order)_ | Path to the root config file. |
| `--format` | `text` \| `json` | `text` | Output format. Use `json` for machine-readable diagnostics in CI. |

**What it checks**

- `eval.yaml` parses against the Pydantic schema without errors.
- Every task file referenced under `tasks:` exists and is valid.
- Each `WorkspaceSpec` has a reachable `git_repo` (for `git_repo` type) or valid file list.
- All `expectations` reference a supported type: `exit_code`, `contains`, `file_exists`, or `command`.
- Isolation level is available on the current platform (warns if Seatbelt/Bubblewrap is missing and falls back to `logical`).

**Examples**

::: code-group

```bash [Default text output]
micro-eval validate
```

```bash [JSON output for CI]
micro-eval validate --format json
```

```bash [Explicit config path]
micro-eval validate --config ./experiments/finetune.yaml
```

:::

**Sample text output**

```
✓ Config loaded: eval.yaml
✓ Tasks: 3 found, 3 valid
✓ Configurations: 2
✓ RunPlan: 6 cells (3 tasks × 2 configs × 1 repetition)
✓ Workspace: git_repo @ HEAD (sha: a1b2c3d)
⚠ Isolation: seatbelt not found — falling back to logical (git worktree)
```

**Exit codes**

| Code | Meaning |
|------|---------|
| `0` | RunPlan is valid and ready to execute. |
| `1` | Unexpected error (filesystem, import failure). |
| `2` | Validation failure — schema errors or missing files; details printed to stderr. |

---

## micro-eval run

Executes the full evaluation matrix: **Tasks × Configurations × Repetitions**. Each cell is a subprocess invocation of the agent under test. Results are written to `.micro-eval/runs/<run-id>/`.

**Synopsis**

```
micro-eval run [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config PATH` | path | _(lookup order)_ | Path to the root config file. |
| `--max-concurrency N` | int | `4` | Maximum number of agent subprocesses running simultaneously. |
| `--dry-run` | flag | `false` | Print the resolved RunPlan and exit without invoking any agent. |
| `--format` | `text` \| `json` | `text` | Progress and summary output format. |

**Execution model**

- The RunPlan is expanded into an ordered list of `(task, config, repetition)` cells.
- Cells run under `asyncio` with bounded concurrency (`--max-concurrency`).
- Each agent is launched with `argv`-only argument passing — no shell string interpolation.
- Secrets matching `MICRO_EVAL_SECRET_*` are passed to the subprocess environment but **redacted** from all logs and stored artifacts.
- After execution, a deterministic validator checks `expectations`; an optional LLM judge runs if configured.

**Isolation levels** (resolved at run time)

| Level | Mechanism | Platform |
|-------|-----------|----------|
| `logical` | git worktree per cell | All |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | macOS / Linux |
| `container` | Container runtime | Requires Docker or equivalent |
| `vm` | E2B / Modal remote sandbox | Requires credentials |

::: warning
If `os_policy` isolation is requested but the platform binary is unavailable, execution falls back to `logical` and records a caveat in the run result. Remote providers (`vm`) do **not** fall back — they fail hard if credentials are missing.
:::

**Examples**

::: code-group

```bash [Default run]
micro-eval run
```

```bash [Lower concurrency]
# Useful when agents are memory-intensive
micro-eval run --max-concurrency 2
```

```bash [Dry run — inspect plan without executing]
micro-eval run --dry-run
```

```bash [JSON output for CI]
micro-eval run --format json
```

```bash [Custom config]
micro-eval run --config ./experiments/finetune.yaml --max-concurrency 8
```

:::

**Passing secrets**

```bash
# Secrets are forwarded to the agent subprocess and redacted from all logs
export MICRO_EVAL_SECRET_API_KEY=sk-...
micro-eval run
```

**Output location**

```
.micro-eval/
└── runs/
    └── <run-id>/
        ├── run.json          # RunResult (scores, decisions, caveats)
        ├── matrix.json       # Full ResultMatrix
        └── artifacts/        # Per-cell stdout, stderr, diffs
```

**Exit codes**

| Code | Meaning |
|------|---------|
| `0` | All cells completed (some may have scored 0; check the matrix). |
| `1` | Execution error — agent launch failed, filesystem error, or unhandled exception. |
| `2` | Validation failure — config or task schema error prevented the run from starting. |

---

## micro-eval list

Lists run records discovered under `.micro-eval/runs/*/run.json`. Useful for finding a `RUN_ID` to pass to `micro-eval report`.

**Synopsis**

```
micro-eval list [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | `text` \| `json` | `text` | Output format. |

**Examples**

::: code-group

```bash [Human-readable table]
micro-eval list
```

```bash [Machine-readable list]
micro-eval list --format json
```

:::

**Sample text output**

```
RUN ID                                STARTED              TASKS  CONFIGS  STATUS
run-20260615-143022-a1b2c3d4          2026-06-15 14:30:22      3        2  complete
run-20260614-091045-f9e8d7c6          2026-06-14 09:10:45      5        2  complete
run-20260613-172300-11223344          2026-06-13 17:23:00      3        3  partial
```

**Exit codes**

| Code | Meaning |
|------|---------|
| `0` | List printed (may be empty if no runs exist). |
| `1` | Error — `.micro-eval/` directory is missing or unreadable. |

---

## micro-eval report

Renders the ResultMatrix for a completed run, including per-cell scores, aggregate statistics, the overall decision, caveats, and artifact references.

**Synopsis**

```
micro-eval report [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--run RUN_ID` | string | _(latest run)_ | Run identifier from `micro-eval list`. Defaults to the most recent run. |
| `--format` | `text` \| `json` \| `html` | `text` | Output format. `html` writes a standalone report file. |
| `--output PATH` | path | `report.html` | Destination file when `--format html` is used. |

**Decision statuses**

| Status | Meaning |
|--------|---------|
| `improved` | New configuration scores higher across all tasks. |
| `regressed` | New configuration scores lower across all tasks. |
| `mixed` | Some tasks improved, others regressed. |
| `inconclusive` | Differences are within the noise threshold. |
| `not_comparable` | Runs used different workspace snapshots or task sets. |
| `needs_human_review` | LLM judge confidence is below threshold; human annotation required. |

**Examples**

::: code-group

```bash [Latest run, text]
micro-eval report
```

```bash [Specific run, JSON]
micro-eval report --run run-20260615-143022-a1b2c3d4 --format json
```

```bash [HTML report to file]
micro-eval report --format html --output ./reports/2026-06-15.html
```

```bash [HTML to custom path]
micro-eval report \
  --run run-20260615-143022-a1b2c3d4 \
  --format html \
  --output /tmp/eval-report.html
```

:::

**Sample text output**

```
Run: run-20260615-143022-a1b2c3d4  (2026-06-15 14:30:22)
Tasks: 3  Configurations: 2  Repetitions: 1

                       config-baseline   config-new
  task: summarize           0.82            0.91  ▲
  task: classify            0.74            0.68  ▼
  task: extract             0.90            0.90  —

Decision: mixed
Caveats:
  - Isolation fell back to logical (seatbelt unavailable)
  - LLM judge used for task:summarize (deterministic score N/A)
```

**Exit codes**

| Code | Meaning |
|------|---------|
| `0` | Report rendered successfully. |
| `1` | Error — run ID not found, or output path is not writable. |
| `2` | Run data is corrupt or missing required fields. |

---

## micro-eval ui

Starts the local Next.js Web UI. The UI reads run data directly from `.micro-eval/` JSON files and never transmits data externally.

::: warning
`micro-eval ui` requires a source checkout of the repository with the `ui/` directory present and Node.js dependencies installed (`cd ui && npm install`). It is not available in a pip-only install.
:::

**Synopsis**

```
micro-eval ui [OPTIONS]
```

**Options**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--port N` | int | `3000` | Local port for the Next.js dev server. |

**Environment variables**

| Variable | Description |
|----------|-------------|
| `MICRO_EVAL_PROJECT_ROOT` | Absolute path to the project whose `.micro-eval/` directory the UI should read. Defaults to the current working directory. |

**Examples**

::: code-group

```bash [Default port]
micro-eval ui
```

```bash [Custom port]
micro-eval ui --port 4000
```

```bash [Point to another project]
MICRO_EVAL_PROJECT_ROOT=/path/to/my-agent-project micro-eval ui --port 3000
```

:::

After startup, open [http://localhost:3000](http://localhost:3000) in your browser.

::: tip
The UI hot-reloads when new runs complete. You can leave it running in a terminal tab while you iterate on `micro-eval run` in another.
:::

**Exit codes**

| Code | Meaning |
|------|---------|
| `0` | Server stopped cleanly (e.g., Ctrl-C). |
| `1` | Error — `ui/` directory not found, Node.js not installed, or port already in use. |

---

## Global Options

These options are accepted by every command:

| Option | Description |
|--------|-------------|
| `--help` | Show help text and exit. |
| `--version` | Print the `micro-eval` version and exit. |

```bash
micro-eval --version
# micro-eval 0.3.2
```

---

## Environment Variables Reference

| Variable | Used by | Description |
|----------|---------|-------------|
| `MICRO_EVAL_CONFIG` | all | Default config path when `--config` is not passed. |
| `MICRO_EVAL_PROJECT_ROOT` | `ui` | Root directory whose `.micro-eval/` the UI reads. |
| `MICRO_EVAL_SECRET_*` | `run` | Secrets forwarded to agent subprocesses; auto-redacted from logs. |
| `LANGFUSE_PUBLIC_KEY` | `run` | Optional Langfuse observability (cost/latency tracing). |
| `LANGFUSE_SECRET_KEY` | `run` | Optional Langfuse observability. |
| `LANGFUSE_HOST` | `run` | Optional Langfuse host override. |

::: danger
Never hard-code secrets in `eval.yaml`. Use `MICRO_EVAL_SECRET_*` environment variables. They are automatically redacted from all stored artifacts and log output.
:::

---

## Quick Reference

```bash
# Scaffold
micro-eval init

# Validate before running
micro-eval validate

# Execute
micro-eval run --max-concurrency 4

# Find the run ID
micro-eval list

# Read the report
micro-eval report --run <RUN_ID> --format html --output report.html

# Open the web UI
micro-eval ui
```
