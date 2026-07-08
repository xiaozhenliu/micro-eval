# Conversational Eval Example Completion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `conversational-eval` example fully runnable — register in the runner, add `run.py`, cover all 5 DeepEval conversational metrics, and add a README.

**Architecture:** The conversational-eval example already has `eval.yaml`, `echo_agent.py`, and one task file. This plan fills the gaps: a `run.py` runner script (same pattern as multi-task-matrix), a smarter mock agent that exercises all conversation paths, an enriched eval.yaml with all 5 metrics, and a README. Since this example requires DeepEval (an external dependency), the `run.py` validates prerequisites and gives clear feedback.

**Tech Stack:** Python 3.11+, DeepEval (conversational metrics), micro-eval CLI

## Global Constraints

- Example must be runnable via `python examples/run-example.py --example conversational-eval`
- No real API keys required for validation; DeepEval metrics require an LLM provider at scoring time
- Follow existing example patterns exactly (run.py CLI flags, `micro_eval_command()` helper, step printing)
- eval.yaml must pass `micro-eval validate`
- All 5 metrics from `METRIC_REGISTRY`: `conversation_completeness`, `turn_relevancy`, `knowledge_retention`, `role_adherence`, `goal_accuracy`

---

### Task 1: Enrich eval.yaml with all 5 conversational metrics

**Files:**
- Modify: `examples/conversational-eval/eval.yaml`

**Interfaces:**
- Consumes: Existing eval.yaml structure
- Produces: Complete eval.yaml with all 5 metrics, `simulator_model` and `turn_timeout_s` fields demonstrated

- [ ] **Step 1: Update eval.yaml**

```yaml
project_name: conversational-eval-example
description: Multi-turn conversational evaluation using DeepEval ConversationSimulator.

configurations:
  - id: echo-agent
    name: "Echo Agent"
    agent:
      name: echo-agent
      command: ["python", "echo_agent.py"]
      input_mode: stdin
      output_mode: stdout

tasks_dir: tasks
output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 1
  timeout_s: 120
  stop_on_cell_error: false

evaluation:
  comparison_subject: "echo agent conversational quality"
  task_set_version: "conversational-eval.v1"
  success_criteria:
    - The agent maintains coherent multi-turn conversation.
    - All 5 conversational metrics are scored.
  required_evaluators: [validator]
  denominator_policy: include_failed
  inconclusive_policy: warn

judge:
  enabled: true
  provider: deepeval_conversational
  max_turns: 5
  turn_timeout_s: 30
  pass_threshold: 0.5
  simulator_model: ""
  conversational_metrics:
    - conversation_completeness
    - turn_relevancy
    - knowledge_retention
    - role_adherence
    - goal_accuracy
  required_secrets: []

trace:
  enabled: true
  provider: process
```

- [ ] **Step 2: Validate the config**

Run: `cd examples/conversational-eval && uv run --project ../.. micro-eval validate --config eval.yaml`
Expected: validation passes (no schema errors)

- [ ] **Step 3: Commit**

```bash
git add examples/conversational-eval/eval.yaml
git commit -m "feat(examples): enrich conversational-eval with all 5 metrics"
```

---

### Task 2: Add a second task to exercise structured rubric

**Files:**
- Create: `examples/conversational-eval/tasks/helpdesk-conversation.yaml`

**Interfaces:**
- Consumes: TaskSpec with conversational fields (scenario, expected_outcome, user_description)
- Produces: A second task that exercises a different scenario and uses a structured `RubricSpec` with dimensions

- [ ] **Step 1: Create the new task file**

```yaml
id: helpdesk-conversation
name: "Helpdesk support conversation"
description: "Test agent handling a multi-step helpdesk scenario with knowledge retention"
input_payload: "You are a customer support agent for a software product."
scenario: "A user reports a bug, provides error details across multiple turns, and asks for a workaround"
expected_outcome: "The agent acknowledges the bug, asks clarifying questions, retains error details, and suggests a workaround"
user_description: "A frustrated but polite user reporting a software crash with stack trace details"
rubric:
  text: "Evaluate whether the agent retains context across turns and provides helpful support"
  dimensions:
    - "Context retention: does the agent remember error details from earlier turns?"
    - "Empathy: does the agent acknowledge the user's frustration?"
    - "Solution quality: does the agent propose a concrete workaround?"
```

- [ ] **Step 2: Validate the config still loads with the new task**

Run: `cd examples/conversational-eval && uv run --project ../.. micro-eval validate --config eval.yaml`
Expected: validation passes, 2 tasks loaded

- [ ] **Step 3: Commit**

```bash
git add examples/conversational-eval/tasks/helpdesk-conversation.yaml
git commit -m "feat(examples): add helpdesk-conversation task with structured rubric"
```

---

### Task 3: Create run.py runner script

**Files:**
- Create: `examples/conversational-eval/run.py`

**Interfaces:**
- Consumes: eval.yaml, echo_agent.py, tasks/*.yaml
- Produces: Runnable script matching multi-task-matrix/run.py pattern (validate → run → list → report)

- [ ] **Step 1: Write run.py**

```python
#!/usr/bin/env python3
"""Run the conversational-eval example.

Demonstrates:
  - Multi-turn conversational evaluation via DeepEval ConversationSimulator
  - JSONL subprocess bridge protocol (echo_agent.py reads/writes JSONL on stdin/stdout)
  - All 5 conversational metrics: conversation_completeness, turn_relevancy,
    knowledge_retention, role_adherence, goal_accuracy
  - Structured RubricSpec with dimensions (helpdesk-conversation task)

Usage:
    python examples/conversational-eval/run.py
    python examples/conversational-eval/run.py --skip-run
    python examples/conversational-eval/run.py --ui

Prerequisites:
    pip install deepeval   # or: uv add deepeval
    export OPENAI_API_KEY=sk-...   # DeepEval metrics require an LLM provider
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

EXAMPLE_NAME = "conversational-eval"


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    example_root = Path(__file__).resolve().parent
    config_name = "eval.yaml"
    command_prefix = micro_eval_command(repo_root)

    if command_prefix is None:
        print(
            "Could not find a runnable micro-eval CLI. Install uv, install micro-eval, "
            "or run this script from a Python environment with the project dependencies.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.max_concurrency < 1:
        print("--max-concurrency must be >= 1", file=sys.stderr, flush=True)
        return 2

    print(f"Running {EXAMPLE_NAME} from {example_root}", flush=True)
    print("This example demonstrates:", flush=True)
    print("  - Multi-turn conversational evaluation (DeepEval ConversationSimulator)", flush=True)
    print("  - JSONL subprocess bridge protocol (echo_agent.py)", flush=True)
    print("  - All 5 conversational metrics", flush=True)
    print("  - Structured RubricSpec with dimensions", flush=True)
    print("", flush=True)
    print("Note: scoring requires DeepEval + an LLM provider (OPENAI_API_KEY).", flush=True)
    print("Without these, validation and structure still work; scoring will be skipped.", flush=True)

    run_step("validate", [*command_prefix, "validate", "--config", config_name], cwd=example_root)
    if not args.skip_run:
        run_step(
            "run",
            [
                *command_prefix,
                "run",
                "--config",
                config_name,
                "--max-concurrency",
                str(args.max_concurrency),
            ],
            cwd=example_root,
        )
    run_step("list", [*command_prefix, "list"], cwd=example_root)
    run_step("text report", [*command_prefix, "report", "--format", "text"], cwd=example_root)
    run_step(
        "HTML report",
        [*command_prefix, "report", "--format", "html", "--output", "report.html"],
        cwd=example_root,
    )

    print(f"\nDone. Static report: {example_root / 'report.html'}", flush=True)
    if args.ui:
        ui_env = {"MICRO_EVAL_PROJECT_ROOT": str(example_root)}
        run_step("UI", [*command_prefix, "ui", "--port", str(args.port)], cwd=repo_root, env_overlay=ui_env)
    else:
        print(
            f"Optional UI: python examples/{EXAMPLE_NAME}/run.py --ui",
            flush=True,
        )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run the {EXAMPLE_NAME} micro-eval example.")
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Validate and regenerate reports from existing runs without re-running.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Maximum concurrent cells (default: 1).",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch the web UI after generating reports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="UI port when --ui is set (default: 3000).",
    )
    return parser.parse_args()


def micro_eval_command(repo_root: Path) -> list[str] | None:
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--project", str(repo_root), "micro-eval"]
    installed_cli = shutil.which("micro-eval")
    if installed_cli:
        return [installed_cli]
    src_dir = repo_root / "src"
    if src_dir.exists():
        return [sys.executable, "-m", "micro_eval.cli.main"]
    return None


def run_step(
    label: str,
    command: Sequence[str],
    *,
    cwd: Path,
    env_overlay: dict[str, str] | None = None,
) -> None:
    print(f"\n==> {label}", flush=True)
    env = os.environ.copy()
    if command[:3] == [sys.executable, "-m", "micro_eval.cli.main"]:
        src_dir = Path(__file__).resolve().parents[2] / "src"
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    if env_overlay:
        env.update(env_overlay)
    result = subprocess.run(list(command), cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the script runs validation**

Run: `python examples/conversational-eval/run.py --skip-run`
Expected: validate step passes (run/report steps may fail without prior run data — that's OK for now)

- [ ] **Step 3: Commit**

```bash
git add examples/conversational-eval/run.py
git commit -m "feat(examples): add run.py for conversational-eval example"
```

---

### Task 4: Register in run-example.py

**Files:**
- Modify: `examples/run-example.py:17-21` (ALL_EXAMPLES list)
- Modify: `examples/run-example.py` parse_args choices

**Interfaces:**
- Consumes: `examples/conversational-eval/run.py` (Task 3)
- Produces: `--example conversational-eval` choice available in run-example.py

- [ ] **Step 1: Add to ALL_EXAMPLES**

In `examples/run-example.py`, change:

```python
ALL_EXAMPLES = [
    "agent-codefix-showdown",
    "multi-task-matrix",
    "git-workspace-isolation",
]
```

to:

```python
ALL_EXAMPLES = [
    "agent-codefix-showdown",
    "multi-task-matrix",
    "git-workspace-isolation",
    "conversational-eval",
]
```

- [ ] **Step 2: Add to argparse choices**

In the `parse_args()` function, change the `--example` choices:

```python
    parser.add_argument(
        "--example",
        choices=["agent-codefix-showdown", "multi-task-matrix", "git-workspace-isolation", "conversational-eval", "all"],
```

- [ ] **Step 3: Verify the integration**

Run: `python examples/run-example.py --example conversational-eval --skip-run`
Expected: dispatches to `examples/conversational-eval/run.py --skip-run`

- [ ] **Step 4: Commit**

```bash
git add examples/run-example.py
git commit -m "feat(examples): register conversational-eval in run-example.py"
```

---

### Task 5: Add README and update coverage matrix

**Files:**
- Create: `examples/conversational-eval/README.md`
- Modify: `examples/README.md` (add row to table, update coverage matrix)

**Interfaces:**
- Consumes: All files created in Tasks 1-4
- Produces: Documentation covering the example's purpose, prerequisites, what to observe

- [ ] **Step 1: Write README.md**

```markdown
# Conversational Evaluation Example

Multi-turn conversational evaluation using DeepEval ConversationSimulator.

## What it demonstrates

- **JSONL subprocess bridge** — `echo_agent.py` reads/writes JSONL on stdin/stdout,
  the same protocol used by `SubprocessBridge` in the engine.
- **All 5 conversational metrics** — `conversation_completeness`, `turn_relevancy`,
  `knowledge_retention`, `role_adherence`, `goal_accuracy`.
- **Structured RubricSpec** — the `helpdesk-conversation` task uses `rubric.dimensions`
  to define evaluation axes, which maps to `ConversationalGEval`.
- **Scenario-driven simulation** — each task declares `scenario`, `expected_outcome`,
  and `user_description` fields that configure the DeepEval simulator.

## Prerequisites

```bash
# DeepEval is required for conversational metrics
pip install deepeval

# Scoring requires an LLM provider
export OPENAI_API_KEY=sk-...
```

Without these, `micro-eval validate` still works (schema validation), but
`micro-eval run` will skip the judge scoring phase.

## Quick start

```bash
# From repository root
python examples/run-example.py --example conversational-eval

# Or directly
python examples/conversational-eval/run.py
python examples/conversational-eval/run.py --ui   # launch web UI after
```

## Files

| File | Purpose |
|---|---|
| `eval.yaml` | Project config with `deepeval_conversational` judge, all 5 metrics |
| `echo_agent.py` | Mock agent: reads JSONL from stdin, echoes back with a canned response |
| `tasks/conversation-task.yaml` | Basic conversation scenario (plain string rubric) |
| `tasks/helpdesk-conversation.yaml` | Helpdesk scenario with structured `RubricSpec` + dimensions |
| `run.py` | One-click runner (validate → run → report) |

## What to observe

1. **JSONL bridge protocol** — the echo agent receives `{"turn": N, "content": "..."}` on
   stdin and responds with the same format. This is the same protocol the engine's
   `SubprocessBridge` uses for real multi-turn agents.

2. **Metric scores** — in the text report and `decision.json`, look for individual metric
   scores (conversation_completeness, turn_relevancy, etc.). The echo agent is simple,
   so scores will be low — that's expected and demonstrates the scoring pipeline works.

3. **Structured rubric** — the `helpdesk-conversation` task uses `rubric.dimensions` which
   triggers `ConversationalGEval` scoring in addition to the standard metrics.
```

- [ ] **Step 2: Update examples/README.md — add to table and coverage matrix**

Add a row to the "Available use cases" table:

```markdown
| [Conversational Evaluation](conversational-eval/) | Multi-turn conversation via DeepEval ConversationSimulator, JSONL subprocess bridge, all 5 conversational metrics, structured RubricSpec with dimensions. Requires DeepEval + LLM provider for scoring. |
```

Add a column to the coverage matrix for `conversational-eval` and add rows for the new capabilities:

```markdown
| Conversational evaluation | | | | ✓ |
| JSONL subprocess bridge | | | | ✓ |
| Structured RubricSpec | | | | ✓ |
```

- [ ] **Step 3: Commit**

```bash
git add examples/conversational-eval/README.md examples/README.md
git commit -m "docs(examples): add conversational-eval README, update coverage matrix"
```
