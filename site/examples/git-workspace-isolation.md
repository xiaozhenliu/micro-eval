# Git Workspace Isolation

The most advanced micro-eval example. Demonstrates every Phase 3 workspace capability in a single runnable scenario: per-cell git worktree isolation, OS policy sandbox, fixture digest and toolchain fingerprint recorded in `SameStartSnapshot`, and cross-run trend analysis with a drift breakpoint.

::: tip Source checkout required
This example lives in the repository under `examples/git-workspace-isolation/`. Clone the repo before running it — it is not bundled into the wheel.
:::

## What You Will Learn

- How the `git_repo` workspace type gives each evaluation cell its own isolated git worktree
- How the OS policy sandbox (`Seatbelt` on macOS, `Bubblewrap` on Linux) wraps agent processes — and how it degrades gracefully when neither is available
- How `fixture_digests` and `toolchain_fingerprint` flow into `SameStartSnapshot` to prove two runs are comparable
- How two runs with different configuration digests produce a drift breakpoint in the trend chart
- How to annotate individual cells with human scores and comments using the Web UI

## Run the Example

::: code-group

```bash [Two runs + reports]
python examples/git-workspace-isolation/run.py
```

```bash [With Web UI]
python examples/git-workspace-isolation/run.py --ui
```

```bash [Reports only (reuse existing runs)]
python examples/git-workspace-isolation/run.py --skip-run
```

:::

The script:

1. Initializes `fixture-repo/` as a git repository (first run only)
2. Runs Pass 1 with `eval.mock.yaml` — `timeout_s: 60`, baseline config digest
3. Runs Pass 2 with `eval.mock.v2.yaml` — `timeout_s: 120`, different config digest, triggers drift breakpoint
4. Generates a text report and `report.html`

## git\_repo Workspace

Every evaluation cell in the result matrix — one cell per `(task, configuration, repetition)` triple — receives its own isolated copy of the fixture repository via `git worktree add --detach`.

### Task configuration

Both tasks in this example share the same workspace declaration:

```yaml{3-9}
workspace:
  type: git_repo
  path: fixture-repo
  ref: HEAD
  fixtures:
    - path: fixture-repo/app.py
  toolchain:
    runtime: python3
    lockfile: requirements.txt
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

### What happens at runtime

For each cell, micro-eval runs:

```bash
git worktree add --detach .micro-eval/workspaces/<cell-id> <commit>
```

The agent's working directory is set to that worktree root. Because every cell starts from the exact same `ref: HEAD` commit:

- Changes one agent makes are invisible to all other agents
- Neither the source `fixture-repo/` nor any other cell's worktree is touched
- All cells start from provably the same code state (captured as `fixture_digests` in `SameStartSnapshot`)

::: tip Agent scripts are inside the fixture repo
The mock agents in this example live at `fixture-repo/scripts/`. Because the agent's cwd is the worktree root (a copy of `fixture-repo/`), the scripts are present in every worktree without any extra setup.
:::

::: warning git required
The `git_repo` workspace type requires `git` on `PATH`. The runner checks for this at startup and exits with a clear error if it is missing.
:::

## OS Policy Sandbox

Requesting OS-level process isolation is a one-line change in the workspace configuration:

```yaml{4-6}
workspace:
  type: git_repo
  path: fixture-repo
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

### Platform behaviour

| Platform | Provider | Mechanism |
|---|---|---|
| macOS | Seatbelt | Deny-by-default sandbox profile wraps the agent process |
| Linux | Bubblewrap | `bwrap` namespace isolation |
| Neither available | Logical (degraded) | git worktree isolation only + caveat recorded |

::: warning Graceful degradation
When neither Seatbelt nor Bubblewrap is available, micro-eval does not fail — it downgrades to `logical` isolation (git worktree only) and records a `caveat` in `same_start_snapshot.sandbox_policy`. The caveat is visible in the Web UI and included in reports so you always know what level of isolation was actually applied.
:::

The `same_start_snapshot.sandbox_policy` field in `run.json` records the level that was used:

```json
{
  "same_start_snapshot": {
    "sandbox_policy": "seatbelt",
    "caveats": []
  }
}
```

On a system where OS policy is unavailable:

```json
{
  "same_start_snapshot": {
    "sandbox_policy": "logical",
    "caveats": ["os_policy requested but Seatbelt/Bubblewrap not available; degraded to logical"]
  }
}
```

## Fixture Digest and Toolchain Fingerprint

micro-eval records two comparability proofs in `SameStartSnapshot` for every `git_repo` run.

### Fixture digest

Derived from the `git_repo` workspace path and the evaluated commit (in this example, `HEAD`). micro-eval computes a SHA-256 over the fixture repository tree at that commit and records it as `fixture_digests`.

```json
{
  "same_start_snapshot": {
    "fixture_digests": {
      "fixture-repo": "sha256:4a7c3b..."
    }
  }
}
```

If you run the same tasks twice, the `fixture_digests` values will be identical — proving both runs saw the same code.

### Toolchain fingerprint

Declared in the task's workspace `toolchain` block:

```yaml
toolchain:
  runtime: python3
  lockfile: requirements.txt
```

micro-eval hashes the `python3` binary and the content of `requirements.txt`, then records the result as `toolchain_fingerprint`.

```json
{
  "same_start_snapshot": {
    "toolchain_fingerprint": "sha256:f8e2a1..."
  }
}
```

Together, `fixture_digests` and `toolchain_fingerprint` give you a verifiable answer to: *did both runs start from the same environment?*

## Trend Analysis and Drift Breakpoints

This example deliberately creates two runs with different configuration digests to demonstrate the drift detection mechanism.

| Pass | Config file | `timeout_s` | Config digest |
|---|---|---|---|
| 1 | `eval.mock.yaml` | `60` | `abc...` (baseline) |
| 2 | `eval.mock.v2.yaml` | `120` | `def...` (changed) |

Because `timeout_s` changed, the configuration digest for Pass 2 differs from Pass 1. micro-eval records a drift caveat on Pass 2 and annotates a **drift breakpoint** between the two runs in the trend chart — a visual signal that results on either side are not directly comparable.

### Querying the trends API

With the Web UI running (`python run.py --ui`), query the trend data for the `refactor-agent-v1` configuration:

```bash
curl "http://localhost:3000/api/trends?config_id=refactor-agent-v1"
```

The response includes a `breakpoints` array marking where the config digest changed:

```json
{
  "config_id": "refactor-agent-v1",
  "data_points": [ ... ],
  "breakpoints": [
    {
      "between_runs": ["run-001", "run-002"],
      "reason": "config_digest_changed",
      "caveat": "timeout_s changed from 60 to 120"
    }
  ]
}
```

::: tip Reading drift breakpoints
A drift breakpoint does not mean results are wrong — it means you should not compare pass rates across the breakpoint as if the conditions were identical. Use the breakpoint to anchor your analysis: improvements after a config change are improvements *under the new config*.
:::

## Human Annotation Guide

The Web UI lets you attach a human score and comment to any cell in the result matrix. Annotations are persisted to `evaluation.json` inside the run directory and are included in subsequent report regenerations.

**Step 1 — Start the Web UI**

```bash
python examples/git-workspace-isolation/run.py --ui
```

**Step 2 — Open the run page**

Navigate to `http://localhost:3000` and click on a run from the list.

**Step 3 — Select a cell**

Click any cell in the result matrix (identified by task × configuration × repetition).

**Step 4 — Add annotation**

In the **AnnotationPanel** on the right side, enter:
- **Score** — a value between `0.0` (fail) and `1.0` (pass)
- **Comment** — free-text reasoning or observations

**Step 5 — Save**

Click **Save**. The annotation is written to `evaluation.json` immediately.

**Step 6 — Regenerate the report**

```bash
# From the example directory:
micro-eval report --format text
```

The annotation score and comment appear in the regenerated report alongside the automated validator result.

::: tip Annotation + automated scoring
Human annotations do not replace the deterministic validator — they layer on top of it. A cell can pass the `contains` check automatically while still receiving a low human score if the output quality is poor.
:::

## File Structure

```
git-workspace-isolation/
├── run.py                          # One-click runner: git init + two passes + reports
├── eval.mock.yaml                  # Pass 1: timeout_s=60 (baseline config digest)
├── eval.mock.v2.yaml               # Pass 2: timeout_s=120 (triggers drift breakpoint)
├── tasks/
│   ├── refactor-extract-function.yaml   # Extract helper functions from app.py
│   └── add-type-hints.yaml              # Add type annotations to app.py
├── fixture-repo/                   # Initialized as a git repo by run.py on first run
│   ├── app.py                      # 60-line monolithic function (source material)
│   ├── requirements.txt            # Toolchain fingerprint source
│   ├── tests/
│   │   └── test_app.py             # pytest tests for app.py
│   ├── .gitignore
│   └── scripts/
│       ├── mock-refactor-agent.py  # Reads stdin, extracts helpers, prints REFACTOR_COMPLETE
│       └── mock-typehint-agent.py  # Reads stdin, adds type hints, prints TYPE_HINTS_ADDED
└── README.md
```

Each worktree created by micro-eval is placed under `.micro-eval/workspaces/<cell-id>/` and cleaned up after the run completes.

## Optional Integrations

These integrations require external credentials. Add the relevant snippet to `eval.mock.yaml` (or `eval.mock.v2.yaml`) to enable them.

### LLM Judge

Enable an LLM judge via DeepEval to score agent output quality beyond the `contains` check:

```yaml
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

### Langfuse Trace

Route cost and latency data to Langfuse for cross-run observability:

```yaml
trace:
  enabled: true
  provider: langfuse
```

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

### Remote VM Isolation (E2B / Modal)

Upgrade isolation from `os_policy` to `vm` for full remote sandbox execution. Change the workspace block in both task files:

```yaml{4-5}
workspace:
  type: git_repo
  path: fixture-repo
  isolation_level: vm
  trust_level: untrusted
```

Then set credentials for your chosen provider:

::: code-group

```bash [E2B]
export E2B_API_KEY=e2b_...
```

```bash [Modal]
export MODAL_TOKEN_ID=...
export MODAL_TOKEN_SECRET=...
```

:::

::: danger No silent downgrade for remote VM
Remote VM providers (`E2B`, `Modal`) fail hard when credentials are absent — there is no automatic fallback to a lower isolation level. This is intentional: silent downgrade would defeat the purpose of requesting `vm` isolation and could silently invalidate your results.
:::
