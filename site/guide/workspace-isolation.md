# Workspace Isolation

Reproducible starting points are micro-eval's core value proposition. If two runs begin from different workspace states, their results cannot be meaningfully compared — even if every other parameter is identical. Workspace isolation is the mechanism that enforces a known, consistent starting point for every cell in the result matrix.

::: tip Since v0.3.0
Workspace types and isolation levels were introduced in Phase 3. Earlier versions used logical isolation (git worktree) implicitly. All four levels are now configurable explicitly.
:::

## Why This Matters

When you run `Tasks × Configurations × Repetitions`, each cell executes in its own workspace. Without isolation:

- A task that writes files can pollute the next repetition
- Two configurations sharing a workspace produce correlated results
- Results from different days are not comparable if the repo drifted

micro-eval tracks a `SameStartSnapshot` for every run — a set of comparability dimensions that must match for two runs to be treated as directly comparable. Workspace state is a first-class dimension in that snapshot.

## Workspace Types

The `workspace` field on a task defines what the agent finds when it starts.

### `blank`

An empty temporary directory. Use this for tasks that do not require pre-existing files — pure generation tasks, API calls, or tasks that create their own scaffolding.

```yaml
workspace:
  type: blank
  isolation_level: logical
```

### `files`

Copies specified files and directories into the task workspace before execution. The file paths are resolved relative to the task YAML file.

```yaml
workspace:
  type: files
  files:
    - ./fixtures/src/utils.py
    - ./fixtures/tests/test_utils.py
    - ./fixtures/pyproject.toml
  isolation_level: logical
```

::: tip Fixture digests
When using `files`, micro-eval computes a SHA-256 digest of each source at run time and records them in `SameStartSnapshot.fixture_digests`. Two runs are only comparable if their fixture digests match.
:::

### `git_repo`

Creates an isolated git worktree at a specific ref. This is the most reproducible option for code-editing tasks — the agent gets a real git history, can create branches, and its changes are fully isolated from your working tree.

```yaml
workspace:
  type: git_repo
  path: .                          # path to the repo (relative to task YAML)
  ref: "abc1234"                   # pin to a specific commit
  isolation_level: logical
  setup:                           # optional: run inside the worktree before the agent starts
    - ["uv", "sync"]
```

::: warning Pinning the ref
Always set `ref` to a full commit SHA for evaluations you intend to compare over time. If `ref` is omitted, micro-eval uses `HEAD` at run time — the workspace will drift as your repo evolves, making historical comparisons unreliable.
:::

## Isolation Levels

The `isolation_level` field on a workspace controls how tightly the agent's process is contained.

| Level | Name | Backend | Availability |
|-------|------|---------|--------------|
| 0 | `logical` | Git worktree | Always available |
| 1 | `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | Host OS dependent |
| 3 | `container` | Reserved | Future |
| 4 | `vm` | E2B / Modal | Requires credentials |

### Level 0 — `logical`

The default. The agent process runs with your full user permissions, but receives an isolated git worktree as its working directory. Changes are contained to the worktree and do not affect your working tree.

This is suitable for trusted agents (your own code) running against your own repositories.

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: logical
```

### Level 1 — `os_policy`

Adds an OS-level sandbox policy around the agent process. This level prevents an agent from accidentally (or intentionally) reading secrets from `~/.ssh`, writing to paths outside the workspace, or modifying your global config files.

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: allowlist
```

::: warning Degradation to logical
If `os_policy` is requested but Seatbelt or Bubblewrap is not available on the host (e.g., Linux without `bwrap` installed), micro-eval **degrades to `logical`** and records a `mixed_isolation` caveat in the run result. The run is not aborted, but the caveat is surfaced in the UI and excluded from strict comparability checks.
:::

### Level 4 — `vm` (Remote Execution)

Runs the agent inside a remote VM provided by E2B or Modal. This is the highest isolation level and is appropriate for:

- Untrusted or adversarial agents
- Agents that need a clean Linux environment regardless of host OS
- Tasks that require specific OS packages or kernel features

```yaml
workspace:
  type: blank
  isolation_level: vm
  trust_level: untrusted
  network_policy: none
```

::: danger Remote providers fail hard
Unlike `os_policy`, remote providers (`e2b`, `modal`) do **not** degrade silently. If credentials are missing or the provider is unreachable, the run fails immediately with an error. This is intentional — a silent downgrade from `vm` to `logical` would defeat the entire purpose of remote isolation.

Set the required credentials as environment variables before running:
:::

```bash
export MICRO_EVAL_SECRET_E2B_API_KEY="your-e2b-key"
export MICRO_EVAL_SECRET_MODAL_TOKEN_ID="your-modal-token-id"
export MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET="your-modal-token-secret"
```

Secrets prefixed with `MICRO_EVAL_SECRET_` are automatically redacted from logs, run artifacts, and LLM judge prompts.

## Trust Levels

The `trust_level` field communicates intent and is used by the provider registry to validate that the chosen isolation level is appropriate.

| Trust level | Recommended isolation | Typical use case |
|-------------|----------------------|------------------|
| `trusted` | `logical` | Your own agents, internal tools |
| `semi_trusted` | `os_policy` | Third-party agents you have reviewed |
| `untrusted` | `vm` | Downloaded agents, external contributors |
| `adversarial` | `vm` | Red-teaming, agents that may attempt escapes |

::: warning Trust is advisory, not enforced
Setting `trust_level: adversarial` does not automatically upgrade the isolation level. You must also set `isolation_level: vm`. Trust is used for documentation, comparability metadata, and future policy enforcement — not as a security gate by itself.
:::

## Network Policy

The `network_policy` field on the workspace controls outbound network access from the agent process. It applies at Level 1 and above.

| Policy | Behavior |
|--------|----------|
| `full` | No network restrictions (default for Level 0) |
| `allowlist` | Only domains listed in `network_allowlist` are reachable |
| `none` | All outbound network access blocked |

```yaml{6-10}
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: allowlist
```

## SameStartSnapshot: Comparability Dimensions

Every run records a `SameStartSnapshot` — a fingerprint of the conditions that produced the results. Two runs are considered directly comparable only if all dimensions match.

| Dimension | What it captures |
|-----------|-----------------|
| `workspace_type` | `blank`, `files`, or `git_repo` |
| `git_commit` | Pinned commit SHA (for `git_repo` workspaces) |
| `fixture_digests` | SHA-256 of each source file (for `files` workspaces) |
| `sandbox_policy` | `logical`, `os_policy`, `vm`, etc. |
| `network_policy` | `full`, `allowlist`, or `none` |
| `toolchain_fingerprint` | Python version, uv lockfile hash, key binary versions |
| `config_hash` | Hash of the configuration block used for this run |

When you compare runs on the trend analysis page, micro-eval marks any pair where a dimension differs as `not_comparable` and surfaces which dimension diverged.

## Complete Configuration Example

::: code-group

```yaml [logical — trusted agent]
configurations:
  - id: claude-code-v1
    agent:
      command: ["claude", "--dangerously-skip-permissions"]
      input_mode: stdin
      timeout_s: 120

tasks:
  - tasks/add-docstrings.yaml
```

```yaml [tasks/add-docstrings.yaml]
id: add-docstrings
name: Add docstrings
input_payload: "Add Google-style docstrings to every public function in src/parser.py."
workspace:
  type: git_repo
  path: .
  ref: "a1b2c3d"
  isolation_level: logical
  trust_level: trusted
```

```yaml [os_policy — semi-trusted agent]
configurations:
  - id: external-agent
    agent:
      command: ["./bin/external-agent", "--mode", "edit"]
      input_mode: stdin
      timeout_s: 180

tasks:
  - tasks/implement-feature.yaml
```

```yaml [tasks/implement-feature.yaml]
id: implement-feature
name: Implement feature
input_payload: "Implement the feature described in SPEC.md."
workspace:
  type: files
  files:
    - ./fixtures/SPEC.md
    - ./fixtures/src/
    - ./fixtures/tests/
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: allowlist
expectations:
  - type: exit_code
    value: 0
  - type: file_exists
    path: src/feature.py
```

```yaml [vm — untrusted agent]
configurations:
  - id: red-team-agent
    agent:
      command: ["./downloaded-agent"]
      input_mode: stdin
      timeout_s: 300
    required_secrets:
      - MICRO_EVAL_SECRET_E2B_API_KEY

tasks:
  - tasks/code-challenge.yaml
```

```yaml [tasks/code-challenge.yaml]
id: code-challenge
name: Code challenge
input_payload: "Solve the algorithmic problem in challenge.txt."
workspace:
  type: files
  files:
    - ./fixtures/challenge.txt
  isolation_level: vm
  trust_level: adversarial
  network_policy: none
expectations:
  - type: contains
    value: "SOLVED"
```

:::

## Next Steps

- [Trend Analysis](/guide/trend-analysis) — track evaluation results over time, detect regressions, and annotate drift breakpoints
