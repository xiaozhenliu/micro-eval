# multi-task-matrix

A micro-eval example that demonstrates the full 2D evaluation matrix with all four expectation types, workspace setup commands, and the caveat system.

## What this example shows

| Capability | Where |
|---|---|
| Multi-task matrix (2 configs × 3 tasks × 2 reps = 12 cells) | `eval.mock.yaml` |
| `exit_code` expectation | `tasks/check-style.yaml` |
| `contains` + `file_exists` expectation | `tasks/find-bugs.yaml` |
| `command` expectation | `tasks/generate-report.yaml` |
| `setup` commands in workspace spec | `tasks/check-style.yaml` |
| Caveat system (partial failure) | `checker-beta` on `generate-report` |
| Mixed decision status | `decision.json` after the run |

## Quick start

```bash
python examples/multi-task-matrix/run.py
```

This runs `validate` → `run` → `list` → text report → HTML report, fully offline. No API keys required.

After the run:
- Open `examples/multi-task-matrix/report.html` to view the matrix in a browser.
- `checker-alpha` (baseline) shows all PASS across all 3 tasks.
- `checker-beta` (candidate) shows FAIL on `generate-report`, PASS on the other two.
- The decision status is `inconclusive` (baseline all-pass vs candidate partial-fail).

## Launch the web UI

```bash
python examples/multi-task-matrix/run.py --ui
```

Opens `http://localhost:3000` with the run matrix, per-cell traces, and the decision panel.

## File structure

```
multi-task-matrix/
├── run.py                          # One-command runner
├── eval.mock.yaml                  # 2 configs × 3 tasks × 2 reps
├── tasks/
│   ├── check-style.yaml            # exit_code expectation + setup commands
│   ├── find-bugs.yaml              # contains + file_exists expectations
│   └── generate-report.yaml        # command expectation
├── workspace/
│   ├── sample-project/
│   │   ├── main.py                 # Data processing with style issues and a hidden bug
│   │   ├── utils.py
│   │   └── tests/test_main.py
│   └── scripts/
│       ├── mock-good-checker.py    # Baseline: passes all three tasks
│       └── mock-flaky-checker.py   # Candidate: fails generate-report intentionally
└── README.md
```

## The four expectation types

### 1. `exit_code` — check-style task

The agent must exit with code 0. Any non-zero exit triggers a FAIL.

```yaml
expectations:
  - type: exit_code
    value: 0
```

### 2. `contains` — find-bugs task

The agent's output file (or stdout) must contain a specific string.

```yaml
expectations:
  - type: contains
    stream: output
    value: "BUG_FOUND"
```

### 3. `file_exists` — find-bugs task

A named file must exist after the run. The `{output_dir}` placeholder scopes the path to the artifact output directory (`MICRO_EVAL_OUTPUT_DIR`), which persists after the workspace is cleaned up. Agents must write durable artifacts to `MICRO_EVAL_OUTPUT_DIR`, not to the workspace CWD.

```yaml
expectations:
  - type: file_exists
    path: "{output_dir}/bugs-report.txt"
```

### 4. `command` — generate-report task

A shell command (specified as an argv list) runs and must exit 0. Use `cwd: "{output_dir}"` to run the command in the artifact output directory where the agent deposited its files.

```yaml
expectations:
  - type: command
    argv: ["python3", "-c", "import json; json.load(open('report/summary.json'))"]
    cwd: "{output_dir}"
    timeout_s: 10
```

This verifies that `report/summary.json` exists and is valid JSON — without the task YAML needing to know the exact JSON schema. The `cwd: "{output_dir}"` scopes the command to the artifact output directory, which persists after workspace cleanup.

## Setup commands

The `check-style` task uses `setup` to verify the workspace is prepared before the agent runs:

```yaml
workspace:
  type: files
  files:
    - workspace
  setup:
    - ["test", "-d", "workspace/sample-project"]
```

Setup commands run in the cell workspace root before the agent starts. They use plain argv arrays — no shell interpolation, no `{python}` placeholder.

## How the inconclusive outcome works

- `checker-alpha` (baseline) completes all three tasks. All 2 × 3 = 6 cells pass. Pass rate: 100%.
- `checker-beta` (candidate) passes `check-style` and `find-bugs`, but skips creating `report/summary.json`. The `command` expectation fails for all 2 repetitions of `generate-report`. Pass rate: 67%.
- The decision shows: `inconclusive (low)` — micro-eval does not yet have a higher-confidence automated decision rule, but the matrix and pass-rate table make the difference visible at a glance.
- The aggregation table shows `@1=67%` for checker-beta vs `@1=100%` for checker-alpha.

## Switching to stdout or directory output

This example uses `output_mode: file` for both configurations. To try other output modes:

**stdout output** — agent writes to stdout instead of a named file:

```yaml
# In eval.mock.yaml, change the agent section:
agent:
  name: My Checker
  command: ["{python}", "workspace/scripts/mock-good-checker.py"]  # no {output_file}
  input_mode: stdin
  output_mode: stdout   # <-- changed
  timeout_s: 30
```

The `{output_file}` placeholder is only injected when `output_mode: file`.

**directory output** — agent writes multiple files; micro-eval captures the whole directory:

```yaml
agent:
  name: My Checker
  command: ["{python}", "workspace/scripts/mock-good-checker.py"]
  input_mode: stdin
  output_mode: directory   # <-- changed
  timeout_s: 30
```

The agent's CWD is treated as the output directory. All files written there are captured as artifacts.
