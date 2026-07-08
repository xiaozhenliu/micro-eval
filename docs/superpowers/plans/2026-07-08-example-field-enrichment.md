# Example Field Enrichment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich existing examples to cover previously unexercised model fields — `blank` workspace, `randomize_execution_order`, `skills_profile`, `parameters`, `input_mode: file`, and `denominator_policy: exclude_failed` — without creating new example directories.

**Architecture:** Rather than new examples, add a second eval config variant to `multi-task-matrix` (`eval.enriched.yaml`) that exercises the uncovered fields. Also add a new task to `agent-codefix-showdown` that uses `blank` workspace + `input_mode: file`. This approach avoids example sprawl while maximizing coverage. The `run.py` for multi-task-matrix gains a `--variant enriched` flag to run the new config.

**Tech Stack:** Python 3.11+, micro-eval CLI, YAML configs

## Global Constraints

- Do not change existing eval.yaml / eval.mock.yaml behavior (backward compatible)
- New configs must pass `micro-eval validate`
- New configs must use deterministic mock agents (no API keys)
- Field enrichment must be meaningful (each field should affect observable output, not just be present for decoration)
- Follow existing file layout conventions

---

### Task 1: Add enriched eval config to multi-task-matrix

**Files:**
- Create: `examples/multi-task-matrix/eval.enriched.yaml`

**Interfaces:**
- Consumes: Existing tasks in `examples/multi-task-matrix/tasks/`, existing workspace scripts
- Produces: A config that exercises `randomize_execution_order`, `skills_profile`, `parameters`, `denominator_policy: exclude_failed`, `inconclusive_policy: block`, and `stop_on_cell_error: true`

- [ ] **Step 1: Create eval.enriched.yaml**

```yaml
# Enriched variant: exercises guardrail and evaluation fields not covered elsewhere.
# Use: python examples/multi-task-matrix/run.py --variant enriched
project_name: multi-task-matrix-enriched
description: >
  Same matrix as eval.mock.yaml but with enriched configuration:
  randomize_execution_order, skills_profile, parameters,
  denominator_policy=exclude_failed, stop_on_cell_error.

configurations:
  - id: checker-alpha
    name: Style Checker Alpha (enriched)
    role: baseline
    repetitions: 2
    skills_profile:
      linter: "ruff"
      formatter: "black"
    parameters:
      strictness: "high"
      max_issues: 10
    agent:
      name: Style Checker Alpha
      command: ["{python}", "workspace/scripts/mock-good-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30
      env: {}
      required_secrets: []

  - id: checker-beta
    name: Style Checker Beta (enriched)
    role: candidate
    repetitions: 2
    skills_profile:
      linter: "pylint"
      formatter: "autopep8"
    parameters:
      strictness: "medium"
      max_issues: 20
    agent:
      name: Style Checker Beta
      command: ["{python}", "workspace/scripts/mock-flaky-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30
      env: {}
      required_secrets: []

tasks:
  - tasks/check-style.yaml
  - tasks/find-bugs.yaml
  - tasks/generate-report.yaml

output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 2
  timeout_s: 60
  output_cap_bytes: 1048576
  artifact_cap_bytes: 1048576
  # Enriched: stop the run as soon as any cell errors
  stop_on_cell_error: true
  # Enriched: randomize cell execution order (seed recorded in run.json)
  randomize_execution_order: true

evaluation:
  comparison_subject: "enriched code quality checker comparison"
  task_set_version: "multi-task-matrix-enriched.v1"
  success_criteria:
    - Alpha (baseline) passes all tasks.
    - Beta (candidate) fails generate-report, but errored cells are excluded from pass rate.
  budget: null
  decision_threshold: null
  # Enriched: block instead of warn on inconclusive
  inconclusive_policy: block
  min_repetitions: 1
  required_evaluators: [validator]
  # Enriched: failed cells are excluded from denominator
  denominator_policy: exclude_failed

trace:
  enabled: true
  provider: process

judge:
  enabled: false
  provider: deepeval
  model: ""
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: []
```

- [ ] **Step 2: Validate the config**

Run: `cd examples/multi-task-matrix && uv run --project ../.. micro-eval validate --config eval.enriched.yaml`
Expected: validation passes

- [ ] **Step 3: Commit**

```bash
git add examples/multi-task-matrix/eval.enriched.yaml
git commit -m "feat(examples): add eval.enriched.yaml to multi-task-matrix"
```

---

### Task 2: Add --variant flag to multi-task-matrix run.py

**Files:**
- Modify: `examples/multi-task-matrix/run.py`

**Interfaces:**
- Consumes: `eval.enriched.yaml` (Task 1), existing `eval.mock.yaml`
- Produces: `--variant enriched` flag that runs the enriched config instead of the default mock

- [ ] **Step 1: Add --variant to parse_args**

In `examples/multi-task-matrix/run.py`, add to `parse_args()`:

```python
    parser.add_argument(
        "--variant",
        choices=["mock", "enriched"],
        default="mock",
        help="Config variant: mock (default) or enriched (exercises extra fields).",
    )
```

- [ ] **Step 2: Update main() to use variant**

In the `main()` function, change `config_name = "eval.mock.yaml"` to:

```python
    variant_configs = {
        "mock": "eval.mock.yaml",
        "enriched": "eval.enriched.yaml",
    }
    config_name = variant_configs[args.variant]
```

And update the print block to show enriched-specific info when applicable:

```python
    print(f"Running {EXAMPLE_NAME} ({args.variant}) from {example_root}", flush=True)
    if args.variant == "enriched":
        print("Enriched variant exercises:", flush=True)
        print("  - randomize_execution_order (cell order randomized, seed in run.json)", flush=True)
        print("  - skills_profile + parameters (per-config metadata, included in config digest)", flush=True)
        print("  - denominator_policy: exclude_failed (errored cells excluded from pass rate)", flush=True)
        print("  - stop_on_cell_error: true (run halts on first cell error)", flush=True)
        print("  - inconclusive_policy: block (inconclusive treated as blocking)", flush=True)
    else:
        print("This example demonstrates:", flush=True)
        print("  - 2 configs × 3 tasks × 2 reps = 12 cells (multi-task matrix)", flush=True)
        print("  - All 4 expectation types: exit_code, contains, file_exists, command", flush=True)
        print("  - Workspace setup commands", flush=True)
        print("  - Checker-beta partial failure (generate-report task)", flush=True)
        print("  - Inconclusive decision (baseline all-pass vs candidate partial-fail)", flush=True)
```

- [ ] **Step 3: Test both variants**

Run: `python examples/multi-task-matrix/run.py --variant mock`
Expected: runs as before (12 cells, inconclusive decision)

Run: `python examples/multi-task-matrix/run.py --variant enriched`
Expected: runs with enriched config (note: stop_on_cell_error may halt early when beta fails)

- [ ] **Step 4: Commit**

```bash
git add examples/multi-task-matrix/run.py
git commit -m "feat(examples): add --variant enriched flag to multi-task-matrix"
```

---

### Task 3: Add blank-workspace task with input_mode file to agent-codefix-showdown

**Files:**
- Create: `examples/agent-codefix-showdown/tasks/blank-workspace-task.yaml`
- Create: `examples/agent-codefix-showdown/workspace/scripts/mock-blank-agent.py`
- Create: `examples/agent-codefix-showdown/eval.blank.yaml`

**Interfaces:**
- Consumes: Existing agent-codefix-showdown directory structure
- Produces: A second eval config that uses `blank` workspace type and `input_mode: file`, demonstrating that the agent receives its input from a temp file rather than stdin

- [ ] **Step 1: Create the blank workspace task**

```yaml
id: blank-workspace-task
name: "Generate code from scratch"
description: "Agent creates a file from a blank workspace, receiving input from a file (input_mode: file)."
input_payload: |
  Create a Python file called solution.py that defines a function
  `fibonacci(n)` which returns the nth Fibonacci number (0-indexed).
  Write the file to the output location.
expectations:
  - type: contains
    stream: output
    value: "def fibonacci"
workspace:
  type: blank
rubric: "The agent should produce a valid Python function."
business_impact_tier: 3
tags: [example, blank-workspace, input-file]
```

- [ ] **Step 2: Create the mock agent for file input**

```python
#!/usr/bin/env python3
"""Mock agent that reads input from a file (input_mode: file)."""
import sys

# In file input mode, argv[1] is the input file, argv[2] is the output file
input_file = sys.argv[1] if len(sys.argv) > 1 else None
output_file = sys.argv[2] if len(sys.argv) > 2 else None

if input_file:
    with open(input_file) as f:
        task_input = f.read()
else:
    task_input = sys.stdin.read()

result = '''def fibonacci(n):
    """Return the nth Fibonacci number (0-indexed)."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
'''

if output_file:
    with open(output_file, "w") as f:
        f.write(result)
else:
    print(result)
```

- [ ] **Step 3: Create eval.blank.yaml**

```yaml
# Demonstrates blank workspace type and input_mode: file.
# The agent receives its task input from a temp file instead of stdin,
# and works in an empty workspace (no pre-existing files).
project_name: agent-codefix-showdown-blank
description: Blank workspace + file input mode demo.

configurations:
  - id: mock-blank
    name: "Mock Blank Agent"
    role: baseline
    repetitions: 1
    agent:
      name: mock-blank
      command: ["{python}", "workspace/scripts/mock-blank-agent.py", "{input_file}", "{output_file}"]
      input_mode: file
      output_mode: file
      timeout_s: 30
      env: {}
      required_secrets: []

tasks:
  - tasks/blank-workspace-task.yaml
output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 1
  timeout_s: 60
  stop_on_cell_error: false

evaluation:
  comparison_subject: "blank workspace + file input mode"
  success_criteria:
    - The agent reads input from a file and produces a valid fibonacci function.
  required_evaluators: [validator]
  denominator_policy: include_failed

trace:
  enabled: true
  provider: process

judge:
  enabled: false
```

- [ ] **Step 4: Validate**

Run: `cd examples/agent-codefix-showdown && uv run --project ../.. micro-eval validate --config eval.blank.yaml`
Expected: validation passes

- [ ] **Step 5: Commit**

```bash
git add examples/agent-codefix-showdown/tasks/blank-workspace-task.yaml
git add examples/agent-codefix-showdown/workspace/scripts/mock-blank-agent.py
git add examples/agent-codefix-showdown/eval.blank.yaml
git commit -m "feat(examples): add blank workspace + file input mode variant"
```

---

### Task 4: Update examples/README.md coverage matrix

**Files:**
- Modify: `examples/README.md`

**Interfaces:**
- Consumes: All changes from Tasks 1-3
- Produces: Updated coverage matrix showing all newly covered fields

- [ ] **Step 1: Add new capability rows to the matrix**

Add these rows to the coverage matrix in `examples/README.md`:

```markdown
| `blank` workspace | ✓ (eval.blank.yaml) | | | |
| `input_mode: file` | ✓ (eval.blank.yaml) | | | |
| `randomize_execution_order` | | ✓ (eval.enriched.yaml) | | |
| `skills_profile` | | ✓ (eval.enriched.yaml) | | |
| `parameters` | | ✓ (eval.enriched.yaml) | | |
| `denominator_policy: exclude_failed` | | ✓ (eval.enriched.yaml) | | |
| `inconclusive_policy: block` | | ✓ (eval.enriched.yaml) | | |
| `stop_on_cell_error: true` | | ✓ (eval.enriched.yaml) | | |
```

- [ ] **Step 2: Add notes about variant configs in the Quick Start section**

After the existing quick start commands, add:

```markdown
### Config variants

Some examples ship multiple config files for different feature coverage:

```bash
# multi-task-matrix: enriched variant (randomize, skills_profile, etc.)
python examples/run-example.py --example multi-task-matrix  # default (mock)
cd examples/multi-task-matrix && uv run micro-eval run --config eval.enriched.yaml

# agent-codefix-showdown: blank workspace + file input mode
cd examples/agent-codefix-showdown && uv run micro-eval run --config eval.blank.yaml
```
```

- [ ] **Step 3: Update the multi-task-matrix description in the use-case table**

Add a note about the enriched variant:

```markdown
| [Multi-Task Matrix](multi-task-matrix/) | 2 configs × 3 tasks × 2 reps = 12-cell matrix with all four expectation types (`exit_code`, `contains`, `file_exists`, `command`), workspace setup commands, and a deliberately partial-failing candidate. **Enriched variant** (`eval.enriched.yaml`) adds `randomize_execution_order`, `skills_profile`, `parameters`, `denominator_policy: exclude_failed`, and `stop_on_cell_error`. |
```

- [ ] **Step 4: Commit**

```bash
git add examples/README.md
git commit -m "docs(examples): update coverage matrix with enriched fields"
```
