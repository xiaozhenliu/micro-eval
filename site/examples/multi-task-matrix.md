# Multi-Task Matrix

Demonstrates a full 2D evaluation matrix: **2 configurations × 3 tasks × 2 repetitions = 12 cells**. All four expectation types are exercised, workspace setup commands run before each agent invocation, and the run intentionally produces an `inconclusive` decision — showing how micro-eval surfaces partial failures rather than hiding them.

::: tip No API keys required
This example runs entirely offline using deterministic mock agents. No LLM credentials, no external services.
:::

## What You Will Learn

- How multi-task evaluation expands into a full result matrix
- All four expectation types (`exit_code`, `contains`, `file_exists`, `command`) and when to use each
- How `setup` commands prepare a workspace before the agent starts
- How the caveat system surfaces partial failures and sets the decision status
- What `inconclusive` means and how to read the pass-rate table

## Run the Example

```bash
# From the repository root
python examples/run-example.py --example multi-task-matrix
```

The launcher runs `validate` → `run` → `list` → text report → HTML report in sequence. After it finishes:

- Open `examples/multi-task-matrix/report.html` in a browser to view the matrix.
- `checker-alpha` (baseline) shows **PASS** across all three tasks.
- `checker-beta` (candidate) shows **FAIL** on `generate-report`, PASS on the other two.
- The overall decision is `inconclusive`.

To explore the result in the web UI instead:

```bash
python examples/run-example.py --example multi-task-matrix --ui
```

This opens `http://localhost:3000` with the full matrix view, per-cell traces, and the decision panel.

## File Structure

```
examples/multi-task-matrix/
├── eval.mock.yaml                  # 2 configs × 3 tasks × 2 reps
├── run.py                          # One-command runner (called by run-example.py)
├── tasks/
│   ├── check-style.yaml            # exit_code expectation + setup commands
│   ├── find-bugs.yaml              # contains + file_exists expectations
│   └── generate-report.yaml        # command expectation
└── workspace/
    ├── sample-project/
    │   ├── main.py                 # Python source with style issues and a hidden bug
    │   ├── utils.py
    │   └── tests/test_main.py
    └── scripts/
        ├── mock-good-checker.py    # Baseline: passes all three tasks
        └── mock-flaky-checker.py   # Candidate: intentionally fails generate-report
```

## The Evaluation Config

The top-level config declares two configurations and references the three task files:

```yaml
project_name: multi-task-matrix-mock
description: Offline smoke showing multi-task matrices, all 4 expectation types, setup commands, and caveats.

configurations:
  - id: checker-alpha
    name: Style Checker Alpha
    role: baseline
    repetitions: 2
    agent:
      name: Style Checker Alpha
      command: ["{python}", "workspace/scripts/mock-good-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30

  - id: checker-beta
    name: Style Checker Beta
    role: candidate
    repetitions: 2
    agent:
      name: Style Checker Beta
      command: ["{python}", "workspace/scripts/mock-flaky-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30

tasks:
  - tasks/check-style.yaml
  - tasks/find-bugs.yaml
  - tasks/generate-report.yaml
```

The `{python}` placeholder resolves to the same Python interpreter that micro-eval is running under. The `{output_file}` placeholder is injected at execution time when `output_mode: file` is set — it points to a file path inside the per-cell artifact output directory.

## The Four Expectation Types

### 1. `exit_code` — check-style task

The simplest contract: the agent process must exit with a specific code. Any other exit code is a FAIL.

```yaml{3-4}
# tasks/check-style.yaml
expectations:
  - type: exit_code
    value: 0
```

Use `exit_code` when the agent is a CLI tool that already signals success or failure through its exit status — linters, test runners, compilers, and similar tools.

### 2. `contains` — find-bugs task

The agent's output (the file written to `{output_file}`, or stdout when `output_mode: stdout`) must contain a specific string.

```yaml{3-5}
# tasks/find-bugs.yaml
expectations:
  - type: contains
    stream: output
    value: "BUG_FOUND"
```

Use `contains` when you want to assert that the agent produced a specific token or marker without caring about the surrounding content. This is useful for agents that emit structured tags like `BUG_FOUND`, `TASK_COMPLETE`, or `VERDICT:`.

### 3. `file_exists` — find-bugs task

A named file must exist in the artifact output directory after the agent finishes. The `{output_dir}` placeholder resolves to `MICRO_EVAL_OUTPUT_DIR` — the per-cell directory that persists after the workspace is cleaned up.

```yaml{3-4}
# tasks/find-bugs.yaml
expectations:
  - type: file_exists
    path: "{output_dir}/bugs-report.txt"
```

::: warning Write artifacts to `MICRO_EVAL_OUTPUT_DIR`, not the workspace CWD
The workspace directory (`workspace/`) is ephemeral and may be cleaned up after the run. Any file the agent writes there will not survive validation. Agents must write durable artifacts — reports, log files, generated code — to the path given by the `MICRO_EVAL_OUTPUT_DIR` environment variable.
:::

### 4. `command` — generate-report task

An arbitrary command (specified as a plain argv list) runs after the agent finishes and must exit 0. The `cwd` field scopes the command to the artifact output directory.

```yaml{3-6}
# tasks/generate-report.yaml
expectations:
  - type: command
    argv: ["python3", "-c", "import json; json.load(open('report/summary.json'))"]
    cwd: "{output_dir}"
    timeout_s: 10
```

This particular command verifies that `report/summary.json` exists **and** is valid JSON — without the task YAML needing to know the exact schema. You can use any program available on the host: `jq`, `diff`, a custom validation script, or a schema validator.

::: tip `command` as a flexible validator
`command` is the most expressive expectation type. Because the argv list is executed directly — no shell interpolation — you can compose validators from any tools on the system path. A non-zero exit from the command means FAIL.
:::

## Workspace Setup Commands

The `check-style` task uses `setup` to run a verification step before the agent starts:

```yaml{4-6}
# tasks/check-style.yaml
workspace:
  type: files
  files:
    - workspace
  setup:
    - ["test", "-d", "workspace/sample-project"]
```

Setup commands run in the cell workspace root, in order, before the agent process starts. Each command is a plain argv list — no shell expansion, no glob patterns, no `{python}` or other placeholders. If any setup command exits non-zero, the cell is marked as an error and the agent does not run.

Use setup commands to:
- Verify required files or directories exist
- Install dependencies (`["pip", "install", "-r", "requirements.txt"]`)
- Run database migrations or seed scripts
- Copy or generate fixture data before the agent touches the workspace

## How the Inconclusive Outcome Works

The example is designed to produce a clear, readable partial failure:

| Configuration | check-style | find-bugs | generate-report | Pass rate |
|---|:---:|:---:|:---:|:---:|
| checker-alpha (baseline) | PASS | PASS | PASS | 100% (6/6 cells) |
| checker-beta (candidate) | PASS | PASS | **FAIL** | 67% (4/6 cells) |

`checker-beta` intentionally skips creating `report/summary.json`. The `command` expectation runs `python3 -c "import json; json.load(open('report/summary.json'))"` in the artifact output directory and receives a `FileNotFoundError`, making both repetitions of the `generate-report` task a FAIL.

The resulting decision status is **`inconclusive`** with a low-confidence signal. micro-eval does not automatically declare a regression from a single failing task when it lacks a configured `decision_threshold`, but it makes the difference visible in the matrix and the pass-rate summary:

```
checker-alpha  @1=100%  (baseline)
checker-beta   @1= 67%  (candidate)
decision: inconclusive (low)
```

::: tip When `inconclusive` is the right outcome
`inconclusive` means micro-eval detected a difference but does not have enough signal to call it a regression or an improvement. Add a `decision_threshold` to the evaluation config, increase `repetitions`, or add an LLM judge to raise confidence and get a sharper decision.
:::

## Guardrails

This example runs with bounded concurrency and per-cell output caps:

```yaml
guardrails:
  max_concurrency: 2
  timeout_s: 60
  output_cap_bytes: 1048576    # 1 MiB per output file
  artifact_cap_bytes: 1048576  # 1 MiB per artifact directory
  stop_on_cell_error: false
```

`stop_on_cell_error: false` allows the run to continue even when individual cells fail — important here because we want `checker-beta` to fail on one task without aborting the entire matrix.

## Switching Output Modes

This example uses `output_mode: file` for both configurations. To try other modes, edit the agent block in `eval.mock.yaml`:

::: code-group

```yaml [file (default)]
agent:
  command: ["{python}", "workspace/scripts/mock-good-checker.py", "{output_file}"]
  input_mode: stdin
  output_mode: file
  timeout_s: 30
```

```yaml [stdout]
agent:
  # Remove {output_file} from the command — the agent writes to stdout instead.
  command: ["{python}", "workspace/scripts/mock-good-checker.py"]
  input_mode: stdin
  output_mode: stdout
  timeout_s: 30
```

```yaml [directory]
agent:
  # The agent's CWD becomes the output directory.
  # All files written there are captured as artifacts.
  command: ["{python}", "workspace/scripts/mock-good-checker.py"]
  input_mode: stdin
  output_mode: directory
  timeout_s: 30
```

:::

The `{output_file}` placeholder is only injected when `output_mode: file`. With `stdout` or `directory` modes, remove it from the `command` list.

## Capability Summary

| Capability demonstrated | Location |
|---|---|
| 2 configs × 3 tasks × 2 reps = 12 cells | `eval.mock.yaml` |
| `exit_code` expectation | `tasks/check-style.yaml` |
| `contains` expectation | `tasks/find-bugs.yaml` |
| `file_exists` expectation | `tasks/find-bugs.yaml` |
| `command` expectation | `tasks/generate-report.yaml` |
| Workspace `setup` commands (argv lists) | `tasks/check-style.yaml` |
| `files` workspace type | All three task files |
| Caveat system (partial failure) | `checker-beta` on `generate-report` |
| `inconclusive` decision status | `decision.json` after the run |
| `stop_on_cell_error: false` guardrail | `eval.mock.yaml` |

## Next Steps

- **Scale up**: add more tasks to the `tasks:` list or increase `repetitions` to see how the matrix grows.
- **Raise confidence**: add a `decision_threshold` to the `evaluation:` block to convert an `inconclusive` outcome into a clear `regressed` or `improved` verdict.
- **Add an LLM judge**: enable `judge.enabled: true` with an OpenAI key to score outputs beyond deterministic expectations.
- **Try workspace isolation**: see the [Git Workspace Isolation](/examples/git-workspace-isolation) example for OS policy sandboxing and fixture digest tracking.
