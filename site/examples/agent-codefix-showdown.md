# Agent Codefix Showdown

The first and simplest micro-eval example. A single Python code-fix task — repair a ledger rounding bug — expanded across a matrix of four local agent CLIs, with a copied `files` workspace, argv-only wrapper commands, and deterministic validation. No LLM judge, no external services.

Run the offline smoke path in about ten seconds, or swap in real agents once your local CLIs are configured.

::: tip Source-checkout example
This example lives under `examples/agent-codefix-showdown/` in the repository. Clone the repo first:
```bash
git clone https://github.com/xiaozhenliu/micro-eval.git
cd micro-eval
```
:::

---

## What You'll Learn

| Topic | Where it appears |
|---|---|
| `configurations[]` matrix | Four configurations in `eval.yaml`, one per agent CLI |
| `files` workspace | Fixture directory copied into a disposable per-cell working directory |
| argv-only wrapper commands | `run-agent.py` and `mock-fix-agent.py` pass input via file, not shell string |
| `contains` expectation | Deterministic validation of a structured output marker |
| Phase 2 trace capture | Process-level wall-clock trace recorded per cell |
| pass@k / pass^k aggregation | Three repetitions in the mock path surface real aggregation metrics |
| `decision.json` | Per-run verdict with `denominator_policy`, caveats, and per-configuration stats |
| Web UI review page | Interactive verdict, matrix heatmap, and cost panel |

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Required |
| micro-eval installed | `uv sync --all-extras` from repo root, or `pip install micro-eval` |
| Node.js 18+ | Optional — only needed for the Web UI (`--ui` flag) |
| Local agent CLIs | Optional — only needed for `--real` mode |

::: tip No model calls required
The default smoke path uses a deterministic local fixer and never calls any LLM. You can run the full example entirely offline.
:::

---

## Run the Example

All three modes are launched from the **repository root** via the cross-platform runner:

::: code-group

```bash [Deterministic smoke (default)]
# No model calls — proves config, task, validation, and reports work.
python examples/run-example.py
```

```bash [Real agent matrix]
# Requires Claude Code, Codex CLI, OpenClaw, and Hermes to be installed and logged in.
python examples/run-example.py --real
```

```bash [Launch Web UI]
# Starts the Next.js UI pointing at this example's .micro-eval/ run store.
python examples/run-example.py --ui
```

:::

After each run, output lands under `examples/agent-codefix-showdown/.micro-eval/runs/` and a static `report.html` is written to the example directory.

---

## File Structure

```text
examples/
├── run-example.py                       # cross-platform one-command runner
└── agent-codefix-showdown/
    ├── eval.yaml                        # real-agent matrix (Claude Code, Codex CLI, OpenClaw, Hermes)
    ├── eval.mock.yaml                   # deterministic smoke — 3 reps, process trace on
    ├── tasks/
    │   └── fix-ledger-rounding.yaml     # task definition: prompt, expectations, workspace ref
    └── workspace/
        ├── ledger.py                    # intentionally buggy fixture
        ├── tests/
        │   └── test_ledger.py           # unittest suite the agent must make pass
        └── scripts/
            ├── run-agent.py             # argv-only real-agent wrapper (dispatches to four CLIs)
            └── mock-fix-agent.py        # deterministic fixer for the smoke path
```

Each cell gets a **fresh copy** of `workspace/` written to `.micro-eval/workspaces/{run_id}/{cell_id}/` and cleaned up after the cell completes. The agent never touches the fixture source.

---

## The Task

The task asks an agent to fix one function in `ledger.py`. The buggy implementation floors each share and silently drops remainder cents:

```python
# ledger.py — intentionally buggy
def split_amount_cents(total_cents: int, weights: list[int]) -> list[int]:
    total_weight = sum(weights)
    return [(total_cents * weight) // total_weight for weight in weights]
```

Splitting 100 cents across three equal weights produces `[33, 33, 33]` — one cent disappears.

The test suite in `tests/test_ledger.py` describes the required behavior:

```python
def test_preserves_total_when_remainder_exists(self) -> None:
    shares = split_amount_cents(100, [1, 1, 1])
    self.assertEqual(sum(shares), 100)      # total must be preserved
    self.assertEqual(shares, [34, 33, 33])  # largest fractional part gets the remainder
```

The task definition in `tasks/fix-ledger-rounding.yaml` wires the prompt to the workspace fixture and declares the validation expectations:

```yaml
id: fix-ledger-rounding
name: Fix ledger rounding
workspace:
  type: files
  files:
    - workspace             # copied from examples/agent-codefix-showdown/workspace/

expectations:
  - type: contains          # wrapper writes this marker after running the test suite
    stream: output
    value: "MICRO_EVAL_TASK_RESULT=PASS"
  - type: contains
    stream: output
    value: "unit_test_exit_code=0"
```

Both expectations are **deterministic** — no LLM needed. The wrapper runs `python -m unittest` inside the copied workspace after the agent finishes and writes the structured markers to the output file.

---

## Configuration Matrix

`eval.yaml` defines four configurations — one per agent CLI. Each shares the same structure:

```yaml{4,8-9}
configurations:
  - id: claude-code
    name: Claude Code
    role: baseline       # first config is the baseline; others are candidates
    repetitions: 1
    agent:
      name: Claude Code
      command: ["{python}", "workspace/scripts/run-agent.py", "claude-code", "{output_file}"]
      input_mode: stdin   # task prompt delivered via stdin
      output_mode: file   # agent result written to {output_file}
      timeout_s: 900
      env: {}
      required_secrets: []

  - id: codex-cli
    name: Codex CLI
    role: candidate
    repetitions: 1
    agent:
      command: ["{python}", "workspace/scripts/run-agent.py", "codex-cli", "{output_file}"]
      # ... identical structure
```

::: tip argv-only invocation
micro-eval never passes arguments through a shell. The `command` list is passed directly to `subprocess` via argv. The placeholders `{python}` and `{output_file}` are substituted by the engine at runtime — no shell interpolation, no injection risk.
:::

The `role` field marks one configuration as the `baseline`. The Decision layer compares every candidate against it.

---

## Deterministic Smoke Path (eval.mock.yaml)

The smoke configuration is identical in structure to `eval.yaml` but uses a single deterministic configuration with three repetitions:

```yaml{7,10}
configurations:
  - id: mock-local
    name: Local mock fixer
    role: baseline
    repetitions: 3          # three reps for real pass@k / pass^k output
    agent:
      command: ["{python}", "workspace/scripts/mock-fix-agent.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 60

trace:
  enabled: true
  provider: process         # wall-clock + exit code per cell, no Langfuse needed
```

The mock fixer always writes the correct implementation and passes the test suite. Running three repetitions gives the report layer enough data to show real pass@k aggregation instead of a `low_sample` caveat.

---

## Phase 2 Surfaces

The smoke path with `repetitions: 3` and `trace.enabled: true` demonstrates every Phase 2 output surface:

### pass@k and pass^k aggregation

The text and HTML reports show per-configuration aggregation. With three passing repetitions the pass@k is 1.0 and there is no `low_sample` caveat:

```
Configuration: mock-local
  repetitions : 3
  pass@1      : 1.000
  pass^3      : 1.000
  decision    : inconclusive   (single config, no candidate to compare)
```

### decision.json

Written next to `run.json` under `.micro-eval/runs/{run_id}/`:

```json
{
  "decision_report_id": "dr-20260615-001",
  "status": "inconclusive",
  "summary": "Single configuration; no candidate to compare against baseline.",
  "caveats": [],
  "per_configuration": {
    "mock-local": {
      "pass_rate": 1.0,
      "repetitions": 3,
      "denominator_policy": "include_failed"
    }
  }
}
```

### TraceRef and cost source

Each cell records a process-level TraceRef (wall clock, exit code). The report annotates cost as unavailable for the mock path:

```
cell: fix-ledger-rounding × mock-local × rep-1
  wall_clock_s  : 0.31
  exit_code     : 0
  cost          : n/a  (no Langfuse trace; no agent-reported cost)
```

Switch to Langfuse by setting `trace.provider: langfuse` and exporting `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`.

### Review page in the Web UI

After producing a run, start the UI:

```bash
python examples/run-example.py --ui
# or: cd ui && npm run dev
```

Then open `http://localhost:3000/run/{run_id}/review` to see:

- **Verdict panel** — DecisionStatus badge with active caveats
- **Matrix heatmap** — Tasks × Configurations grid colored by pass rate
- **Cell detail** — per-cell stdout, trace, cost, and artifact links
- **Cost panel** — per-configuration cost summary (populated when Langfuse is configured)

---

## Upgrading to Real Agents

Install and authenticate each local CLI, then run:

```bash
python examples/run-example.py --real
```

The `--real` flag points the runner at `eval.yaml` instead of `eval.mock.yaml`. Concurrency is capped at 1 by default to avoid surprise token spend and provider rate-limit spikes during first use.

Each agent is dispatched through `workspace/scripts/run-agent.py`, which selects the right CLI invocation based on the first argv argument:

```bash
# What the engine actually runs for the claude-code cell:
python workspace/scripts/run-agent.py claude-code /path/to/output_file
# stdin carries the task prompt
```

The wrapper exits 0 and writes `MICRO_EVAL_TASK_RESULT=PASS` to the output file only if the copied workspace's unittest suite passes after the agent's turn. Any other outcome writes `MICRO_EVAL_TASK_RESULT=FAIL`.

---

## Enabling the Optional LLM Judge

The judge is disabled by default. Enable it in `eval.yaml` to supplement deterministic validation:

```yaml{2-3}
judge:
  enabled: true
  provider: deepeval
  model: "gpt-4o"
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_KEY]
```

```bash
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
```

::: warning Judge never overrides deterministic failures
The LLM judge score is additive evidence. A cell that fails a `contains` expectation cannot be rescued by a high judge score — deterministic validation takes precedence.
:::

---

## Security Caveats

::: warning No network isolation in MVP
This example runs agent CLIs directly on your machine. Agents may access external services, write files outside the workspace copy, or consume network resources according to their own configuration. The MVP does not enforce syscall-level network restrictions.
:::

**What micro-eval does protect:**

- Each cell receives a **fresh copy** of `workspace/` in a disposable temporary directory. The fixture source is never modified.
- Agent subprocesses receive a **narrow environment** — `PATH`, `HOME`, temp directory variables, and `NO_COLOR` only. Broad environment credentials are not forwarded.
- **`MICRO_EVAL_SECRET_*` variables** declared in `required_secrets` are injected at runtime and **auto-redacted** from all logs, traces, and stored artifacts.
- Output is capped at `output_cap_bytes` and artifact size at `artifact_cap_bytes` to prevent runaway writes.

**What you must handle:**

- Do not put high-privilege credentials (cloud provider keys, production tokens) into the environment when running real agents.
- Do not put sensitive data in task prompts — some CLI wrappers pass prompt text as argv for local CLI compatibility.
- Inspect artifacts under `.micro-eval/runs/` before sharing reports.
- If your agents need secrets, use the `MICRO_EVAL_SECRET_` channel — never hardcode values into YAML, prompts, or fixture files.

For stronger isolation, see [Git Workspace Isolation](/examples/git-workspace-isolation), which demonstrates OS-policy sandboxing (Seatbelt on macOS, Bubblewrap on Linux) and remote VM execution via E2B/Modal.

---

## Next Steps

- **[Multi-Task Matrix](/examples/multi-task-matrix)** — expand to a 2 × 3 × 2 cell matrix with all four expectation types and setup commands
- **[Git Workspace Isolation](/examples/git-workspace-isolation)** — Phase 3 sandbox, fixture digest, toolchain fingerprint, and trend analysis
- **[Tasks reference](/guide/tasks)** — full task schema including all expectation types and rubric fields
- **[Configuration reference](/guide/configuration)** — complete `eval.yaml` field documentation
