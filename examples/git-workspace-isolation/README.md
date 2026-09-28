# git-workspace-isolation

Example demonstrating micro-eval's advanced workspace and trend-analysis features.

**Covered capabilities:**

| Capability | Description |
|---|---|
| `git_repo` workspace | Every evaluation cell runs inside an isolated git worktree copy of the repo |
| OS policy sandbox | Requests Seatbelt (macOS) / Bubblewrap (Linux) isolation; gracefully degrades to `logical` |
| Fixture digest | SHA-256 of the fixture repo at the pinned commit, recorded in `SameStartSnapshot` |
| Toolchain fingerprint | `python3` runtime + `requirements.txt` hash, also in `SameStartSnapshot` |
| Trend analysis | Two runs with different config digests produce a drift breakpoint in the trend chart |
| Human annotation | Step-by-step guide below for adding manual scores in the UI |
| `stdout` output mode | Agent prints output directly to stdout (no output file argument needed) |
| `contains` expectation | Both tasks use `contains` to verify the completion marker in stdout |

## Quick start

```bash
# From the micro-eval repo root:
python examples/git-workspace-isolation/run.py
```

This will:
1. Initialize `fixture-repo/` as a git repo (first run only)
2. Run a first evaluation pass with `eval.mock.yaml` (timeout_s=60)
3. Run a second evaluation pass with `eval.mock.v2.yaml` (timeout_s=120, triggers drift)
4. Generate text + HTML reports

To open the Web UI after the runs:

```bash
python examples/git-workspace-isolation/run.py --ui
```

## How it works

### `git_repo` workspace

The task YAML files specify:

```yaml
workspace:
  type: git_repo
  path: fixture-repo
  ref: HEAD
```

For each evaluation cell, micro-eval runs `git worktree add --detach <path> <commit>` to create
an independent, isolated copy of `fixture-repo/`. Every cell starts from the exact same git commit.
Changes made by one agent cell are invisible to all other cells and do not touch `fixture-repo/` itself.

**Important for scripting:** the agent's working directory is the worktree root (a copy of `fixture-repo/`).
That is why the mock agent scripts live at `fixture-repo/scripts/` — they are present in every worktree.

### OS policy sandbox (Seatbelt / Bubblewrap)

The task YAML requests OS-level isolation:

```yaml
workspace:
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

Runtime behaviour:
- **macOS**: the Seatbelt provider wraps the agent process with a deny-by-default sandbox profile
- **Linux**: the Bubblewrap provider uses `bwrap` for namespace isolation
- **Neither available**: graceful downgrade to `logical` isolation (git worktree only) + caveat recorded

The `same_start_snapshot.sandbox_policy` field in `run.json` records which level was actually used.

### Fixture digest and toolchain fingerprint

The task YAML declares:

```yaml
workspace:
  type: git_repo
  path: fixture-repo
  ref: HEAD
  toolchain:
    runtime: python3
    lockfile: requirements.txt
```

micro-eval records these in `SameStartSnapshot`:
- `fixture_digests`: SHA-256 of the fixture repo at the evaluated git commit (derived from the `git_repo` workspace path and HEAD commit, not from a separate `fixtures` list)
- `toolchain_fingerprint`: hash of `python3` binary + `requirements.txt` content

These fields make it possible to prove two runs are comparable — same code, same dependencies.

### Trend analysis and drift breakpoints

`run.py` executes two runs:

| Run | Config file | `timeout_s` | Config digest |
|-----|-------------|-------------|---------------|
| 1 | `eval.mock.yaml` | 60 | `abc...` |
| 2 | `eval.mock.v2.yaml` | 120 | `def...` (different) |

Because `timeout_s` changed, the configuration digest differs. micro-eval records a **drift caveat**
on the second run. In the trend chart at `/api/trends`, a **drift breakpoint** is annotated between
the two runs, signalling that their results are not directly comparable.

To inspect the trends data:

```bash
# With the UI running (python run.py --ui):
curl http://localhost:3000/api/trends?config_id=refactor-agent-v1
```

### Human annotation (step-by-step)

1. Start the UI:
   ```bash
   python examples/git-workspace-isolation/run.py --ui
   ```
2. Open `http://localhost:3000` and navigate to a run.
3. Click on any cell in the result matrix.
4. In the **AnnotationPanel** on the right, add a score (0–1) and a comment.
5. Click **Save**. The annotation is persisted to `evaluation.json` inside the run directory.
6. Re-generate the text report to see the annotation:
   ```bash
   # From examples/git-workspace-isolation/:
   micro-eval report --format text
   ```

## File structure

```
git-workspace-isolation/
├── run.py                          # One-click runner (git init + two runs + reports)
├── eval.mock.yaml                  # Config v1: timeout_s=60
├── eval.mock.v2.yaml               # Config v2: timeout_s=120 (triggers drift breakpoint)
├── tasks/
│   ├── refactor-extract-function.yaml
│   └── add-type-hints.yaml
├── fixture-repo/                   # Initialized as git repo by run.py on first run
│   ├── app.py                      # 60-line monolithic function, no type hints
│   ├── requirements.txt            # toolchain fingerprint source
│   ├── tests/test_app.py           # pytest tests for app.py
│   ├── .gitignore                  # excludes .micro-eval/, __pycache__, *.pyc
│   └── scripts/
│       ├── mock-refactor-agent.py  # Mock agent: extracts helper functions, prints REFACTOR_COMPLETE
│       └── mock-typehint-agent.py  # Mock agent: adds type hints, prints TYPE_HINTS_ADDED
└── README.md
```

## Advanced: optional external integrations

### LLM Judge (DeepEval)

Add to either `eval.mock.yaml`:

```yaml
judge:
  enabled: true
  provider: deepeval
  model: "gpt-4o"
  temperature: 0.0
  pass_threshold: 0.5
  required_secrets: [MICRO_EVAL_SECRET_OPENAI_KEY]
```

Set the secret:

```bash
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
```

### Langfuse trace

```yaml
trace:
  enabled: true
  provider: langfuse
```

Set credentials:

```bash
export LANGFUSE_PUBLIC_KEY=...
export LANGFUSE_SECRET_KEY=...
export LANGFUSE_HOST=https://cloud.langfuse.com
```

### Remote VM isolation (E2B / Modal)

Change the workspace isolation level in the task YAML:

```yaml
workspace:
  isolation_level: vm
  trust_level: untrusted
```

Set credentials:

```bash
export E2B_API_KEY=e2b_...
# or
export MODAL_TOKEN_ID=...
export MODAL_TOKEN_SECRET=...
```

Note: without credentials, remote VM providers fail hard (no silent downgrade).
