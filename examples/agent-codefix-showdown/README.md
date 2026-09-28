---
title: Agent Codefix Showdown
doc_type: tutorial
status: active
created_at: 2026-06-03T10:18+08:00
updated_at: 2026-06-12T20:20+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - examples
  - onboarding
  - mvp
  - agents
related:
  - examples/README.md
  - docs/DEVELOPMENT.md
  - docs/engineering/security-guidelines.md
---

# Agent Codefix Showdown

This source-checkout example lets a new `micro-eval` user run a complete MVP
use case without writing their own `eval.yaml`, task, or fixture workspace.

> Scope and honesty note: this example is a repository/source asset for the
> current MVP. It is not bundled into the wheel, and the interactive Next.js UI
> still needs a source checkout. The CLI and static HTML report path work from
> this example directory after `micro-eval` is installed.

## What this use case demonstrates

- Canonical `configurations[]` matrix.
- One task expanded across local agent configurations.
- A copied `files` workspace for each cell.
- argv-only wrapper commands.
- Deterministic validator expectations.
- `list`, text report, HTML report, and optional source-checkout UI viewing.
- Phase 2: repetitions aggregation (pass@k / pass^k via the mock path),
  process-level trace capture, an independent `decision.json`, and the
  review page in the source-checkout UI.

The task asks an agent to fix a tiny Python ledger rounding bug. The wrapper
then runs the copied workspace's unittest suite with the current Python
interpreter and writes `MICRO_EVAL_TASK_RESULT=PASS` only when those tests pass.

This marker is MVP smoke/use-case validation. It is **not** a benchmark-quality
winner signal; review artifacts and caveats before making decisions.

## Prerequisites

- Python 3.11+.
- `micro-eval` installed, or run through `uv run --project ../..` from this
  source checkout.
- For the real-agent matrix: usable local CLIs for `claude`, `codex`,
  `openclaw`, and `hermes`.

No secrets are hardcoded in this example. If your local agent CLIs need
credentials, configure them through their own login/setup flows. Do not put
high-privilege credentials into this example workspace.

## Fast deterministic smoke

From the repository root, use this path to prove the example, task, validation,
run store, and reports work without model calls:

```bash
python examples/run-example.py
```

The script runs from this example directory, so `.micro-eval/runs` and
`report.html` are written here. During each cell, the agent cwd is also created
under `.micro-eval/workspaces/{run_id}/{cell_id}/` in this example directory and
then cleaned up. Open `examples/agent-codefix-showdown/report.html` in a browser
to inspect the static report.

### What Phase 2 adds to this smoke run

The mock path runs `repetitions: 3` with process trace capture enabled, so a
single smoke run demonstrates the Phase 2 surfaces:

- **pass@k / pass^k** — the text and HTML reports show per-configuration
  aggregation instead of a single pass rate; with 3 successful repetitions
  there is no `low_sample` caveat.
- **`decision.json`** — written next to `run.json` under
  `.micro-eval/runs/{run_id}/`, with a `decision_report_id` and
  per-configuration stats including `denominator_policy`.
- **TraceRef + cost source** — each cell records a process-level trace
  (wall clock, exit code); the report annotates cost as unavailable unless a
  Langfuse trace or agent-reported cost exists (see `trace:` in
  `eval.mock.yaml` for switching providers).
- **Review page** — with the source-checkout UI running, open
  `http://localhost:3000/run/{run_id}/review` for the verdict, caveats,
  matrix heatmap, and cost panel.

The optional LLM judge (`judge:` block) stays disabled here to keep the smoke
path offline. When enabled it only supplements deterministic validation and
never overrides a deterministic failure.

## Real-agent run

From the repository root, run this when all four agent CLIs are installed and
logged in:

```bash
python examples/run-example.py --real
```

Why `--max-concurrency 1`? It avoids surprise token spend, local resource
contention, and provider rate-limit spikes during first use.

## Optional source-checkout UI

The current MVP UI is launched from the repository source tree. From the
repository root, after producing a run in this example directory:

```bash
python examples/run-example.py --ui
```

Then open `http://localhost:3000`.

## Files

```text
agent-codefix-showdown/
├── ../run-example.py      # cross-platform one-command runner
├── eval.yaml              # real Claude Code / Codex CLI / OpenClaw / Hermes matrix
├── eval.mock.yaml         # deterministic local smoke on the same task
├── tasks/
│   └── fix-ledger-rounding.yaml
└── workspace/
    ├── ledger.py          # intentionally buggy fixture
    ├── tests/test_ledger.py
    └── scripts/
        ├── run-agent.py   # argv-only real-agent wrapper
        └── mock-fix-agent.py
```

## Security caveats

- MVP does not provide network isolation. Agent CLIs may access external services
  according to their own configuration.
- The workspace is copied into a disposable temporary directory per cell, but the
  agent still runs on your machine.
- Do not expose high-privilege credentials to evaluated agents.
- Some real-agent wrappers pass task text as argv for local CLI compatibility.
  Do not put sensitive data in task prompts; if your CLI supports stdin-only
  prompts, adapt the wrapper before evaluating sensitive tasks.
- The real-agent wrapper passes a narrow child-process environment
  (`PATH`/`HOME`/temp/lang variables plus `NO_COLOR`). Prefer each CLI's login
  or local config flow over broad environment credentials.
- If you need secrets, use `MICRO_EVAL_SECRET_*` names declared in a config;
  do not hardcode them into YAML, prompts, or fixture files.
- Outputs and artifacts are persisted under `.micro-eval/runs/`; inspect them
  before sharing reports.
