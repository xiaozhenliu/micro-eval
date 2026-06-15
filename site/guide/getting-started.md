# Getting Started

This guide walks you through installing micro-eval and running your first evaluation in under ten minutes.

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Required for CLI and engine |
| [uv](https://docs.astral.sh/uv/) | latest | Recommended package manager |
| Node.js | 18+ | Optional — only needed for the Web UI |

::: tip Why uv?
micro-eval uses `uv` for fast, reproducible dependency resolution. If you prefer `pip`, see the alternative install commands below.
:::

## Installation

### From Source

```bash
git clone https://github.com/xiaozhenliu/micro-eval.git
cd micro-eval
```

Install Python dependencies:

::: code-group

```bash [uv (recommended)]
uv sync --all-extras
```

```bash [pip]
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[all]"
```

:::

Install Web UI dependencies (optional):

```bash
cd ui && npm install && cd ..
```

Verify the CLI is available:

```bash
uv run micro-eval --version
# micro-eval 0.3.2
```

::: tip Shell alias
Add `alias micro-eval="uv run micro-eval"` to your shell profile to skip typing `uv run` each time. The examples below assume this alias is set.
:::

---

## First Evaluation Walkthrough

The walkthrough uses the built-in scaffold to evaluate a simple command — no external APIs needed.

### 1. Initialize a project

Run `init` inside any directory you want to use as your evaluation workspace:

```bash
micro-eval init --force
```

This generates two files:

```
eval.yaml          ← top-level project configuration
tasks/
  hello.yaml       ← a sample task definition
```

Take a look at what was created:

```yaml
# eval.yaml
project_name: my-eval

configurations:
  - id: baseline
    name: baseline
    role: baseline
    repetitions: 1
    agent:
      command: ["echo", "hello world"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 30

tasks:
  - tasks/hello.yaml

guardrails:
  max_concurrency: 2
  timeout_s: 30

evaluation:
  required_evaluators: [validator]
```

```yaml
# tasks/hello.yaml
id: hello
name: Hello echo
input_payload: "hello world"
workspace:
  type: blank

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "hello"
```

::: tip Workspace types
`blank` starts with an empty working directory. Other options are `files` (copy a local directory in) and `git_repo` (clone a repo at a specific commit). See [Core Concepts](/guide/core-concepts) for details.
:::

### 2. Validate your configuration

Before running, confirm that your config and tasks are well-formed and preview the execution plan:

```bash
micro-eval validate
```

Example output:

```
✓ eval.yaml      valid
✓ tasks/hello.yaml  valid

RunPlan
  Configurations : 1  (baseline)
  Tasks          : 1  (hello)
  Repetitions    : 1
  Total cells    : 1
```

::: warning Fix errors before running
`validate` catches schema errors, missing task files, and invalid expectation types. Always run it after editing `eval.yaml` or any task file.
:::

### 3. Execute the matrix

```bash
micro-eval run --max-concurrency 2
```

micro-eval expands `Tasks × Configurations × Repetitions` into a matrix of cells and executes them concurrently (bounded by `--max-concurrency`):

```
Running 1 cell(s) with concurrency 2 …

  [1/1] hello × baseline × rep-1   ✓  0.12s

Run complete  run_id=r-20260615-001
  Passed  : 1
  Failed  : 0
  Decision: inconclusive (single configuration — add a candidate to compare)
```

Each cell runs your command as a subprocess with argv-only argument passing — no shell interpolation.

### 4. List past runs

```bash
micro-eval list
```

```
run_id           started              tasks  configs  status
r-20260615-001   2026-06-15 09:01:03  1      1        complete
```

### 5. View a text report

```bash
micro-eval report --format text
```

```
Run r-20260615-001  ·  2026-06-15 09:01:03
Decision: inconclusive

┌──────────────┬────────────┬────────┬────────────┐
│ task         │ config     │ score  │ status     │
├──────────────┼────────────┼────────┼────────────┤
│ hello        │ baseline   │ 1.00   │ passed     │
└──────────────┴────────────┴────────┴────────────┘
```

### 6. Export an HTML report

```bash
micro-eval report --format html --output report.html
```

Open `report.html` in any browser for a self-contained, shareable report with a full result matrix and per-cell details.

---

## Running the Built-in Example

The repo ships a runnable example that demonstrates a multi-configuration comparison:

```bash
python examples/run-example.py
```

This runs a small evaluation matrix end-to-end and prints the decision to stdout. It's a good reference for what a real `eval.yaml` looks like with multiple configurations and tasks.

---

## Starting the Web UI

The Web UI provides a browser-based view of all runs stored in `.micro-eval/`:

```bash
micro-eval ui --port 3000
```

Then open [http://localhost:3000](http://localhost:3000).

::: tip Local-only
The Web UI is strictly local — it reads `.micro-eval/` JSON files directly and makes no outbound network requests. Node.js 18+ must be installed and `cd ui && npm install` must have been run during setup.
:::

The UI shows:
- **Runs list** — all past runs with status and decision
- **Matrix view** — the full Tasks × Configurations result grid
- **Cell detail** — per-cell trace, stdout/stderr, cost, and annotations
- **Trend chart** — score trends across runs with drift breakpoints

---

## Inspecting Results on Disk

Every run is stored as plain JSON under `.micro-eval/runs/{run_id}/`:

```
.micro-eval/
└── runs/
    └── r-20260615-001/
        ├── run.json        ← run metadata, config snapshot, timings
        ├── decision.json   ← decision status + per-dimension scores
        ├── manifest.json   ← list of all cells with their file paths
        └── cells/
            └── hello__baseline__rep-1/
                ├── result.json   ← exit code, stdout, stderr, score
                └── trace.json    ← Langfuse trace (if configured)
```

**Key files:**

`run.json` — top-level record including the full configuration snapshot used for this run, start/end timestamps, and the resolved task list.

`decision.json` — the run-level verdict. Decision status is one of: `improved`, `regressed`, `mixed`, `inconclusive`, `not_comparable`, or `needs_human_review`.

`cells/` — one subdirectory per `(task, configuration, repetition)` triple. `result.json` holds the raw subprocess output and computed scores against each expectation. `trace.json` appears only when Langfuse is configured.

::: tip SQLite index
micro-eval maintains a SQLite index at `.micro-eval/index.db` for fast trend queries. The JSON files are always the source of truth — the index can be rebuilt at any time from them.
:::

---

## Next Steps

- **[Core Concepts](/guide/core-concepts)** — understand Tasks, Configurations, Runs, and the result matrix in depth
