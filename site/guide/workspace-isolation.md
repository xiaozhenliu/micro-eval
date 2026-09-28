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

Local providers create an isolated git worktree at a specific ref. The agent gets git history and can create branches. Remote providers materialize that ref locally, then upload its files without `.git` or development control directories; remote agents do not receive the repository's git history.

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
| 3 | `container` | Modal | Requires SDK and credentials |
| 4 | `vm` | E2B | Requires SDK and credentials |

### Level 0 — `logical`

The default. The agent process runs with your full user permissions and receives its cell workspace as its working directory. Relative writes stay in that workspace, but this level does not prevent access to other host paths or the network.

This is suitable for trusted agents (your own code) running against your own repositories.

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: logical
```

### Level 1 — `os_policy`

Runs setup, the single-turn agent, and command validators through the same Seatbelt or Bubblewrap execution context. Host writes are limited to the current cell workspace and a separate per-cell output staging directory; run metadata and sibling cell workspaces are not writable. Seatbelt permits broad host reads; Bubblewrap exposes read-only runtime and project roots. Neither provider promises confidentiality for readable host files.

```yaml
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

::: warning Degradation to logical
If `os_policy` is requested but Seatbelt or Bubblewrap is not available on the host (e.g., Linux without `bwrap` installed), micro-eval **degrades to `logical`** and records the unavailable provider and effective isolation in a run caveat. The cell's snapshot gate is marked with a warning; inspect that caveat before comparing results.
:::

Once an OS provider is selected, wrapper startup, unsupported policy, and execution failures fail the cell without an unsandboxed retry. `full` permits network access; `none` denies it. `allowlist` is rejected because explicit rules are not implemented.

### Levels 3 and 4 — Remote Execution

`container` selects Modal and `vm` selects E2B. Each cell owns one remote sandbox, reused for workspace preparation, setup, the single-turn agent, and command validators. Workspace inputs and output artifacts cross the provider's bounded file-transfer interface; local host paths are not treated as remote paths. Remote commands must be installed in the sandbox or supplied with the workspace.

Install the provider extra: `uv pip install 'micro-eval[e2b]'`, `uv pip install 'micro-eval[modal]'`, or `uv pip install 'micro-eval[remote]'` for both. The supported SDK versions are pinned to `e2b==2.31.0` and `modal==1.5.5`.

Remote input transfer accepts regular files only, up to 4,096 entries and 50 MiB in total. Output transfer also respects the configured artifact byte limit. Links, special files, path escapes, and development control directories such as `.git` and `.micro-eval` are not transferred.

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

Declared agent secrets are redacted from captured text. Provider control credentials stay in the host environment; remote commands reject those credential names and values, including when listed in agent `required_secrets`.

Remote network policy defaults to `none`; `full` and `none` are applied when the sandbox is created, with requested and effective policy recorded separately. `allowlist` is rejected. Offline SDK contract tests verify calls against the supported SDK interfaces; they do not prove live service isolation. Credentialed live probes are optional and must be reported separately.

Remote sandboxes have a 3,600-second lifetime, which is a recovery bound rather than evidence that explicit cleanup succeeded. If creation or termination cannot be confirmed, the result reports an unknown allocation or termination state instead of claiming success. The credentialed checks in `tests/e2e/test_remote_provider_live.py` require explicit opt-in and are skipped by default.

Remote git observation is currently unavailable. The result records that limitation instead of asserting a verified same start or an empty diff. Local post-agent observation occurs before validators, so validator writes do not become agent changes.

After a timeout terminates a remote sandbox, its output artifacts are no longer available for download; the result records that transfer limitation.

Remote output inventory is bounded to 512 KiB of encoded metadata; additional entries are omitted and reported as truncated. An invalid control response that exceeds its receive limit fails closed and triggers sandbox cleanup. Each output file is downloaded completely and atomically or omitted.

For local single-turn commands, timeout and cancellation send TERM, then KILL, to the process group. Descendants that leave the group are not covered. Remote timeout and cancellation explicitly terminate the cell sandbox; normal completion also performs cleanup, and failures are recorded rather than hidden.

Multi-turn conversations currently support only `logical`. The cell context opens its provider's persistent interactive bridge, separate from single-turn command execution. Selecting another isolation level is rejected before workspace preparation because it does not support that bridge.

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

The `network_policy` field applies to setup, the single-turn agent, and command validators in the selected OS or remote provider. `logical` does not enforce network restrictions. An unavailable OS provider may degrade to `logical`, so check the effective isolation and caveats.

| Policy | Behavior |
|--------|----------|
| `full` | Provider permits network access; default for OS policy |
| `allowlist` | Rejected by OS and remote providers; explicit rules are not implemented |
| `none` | Seatbelt denies network operations; Bubblewrap creates an isolated network namespace; remote providers disable outbound access. Default for remote providers. |

```yaml{6-10}
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
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
  network_policy: none
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

---

## Server Mode: Workspace-Level Isolation

In server mode (`micro-eval serve`), an additional isolation layer sits above cell-level workspace isolation:

**Server workspaces** are isolated directories under `~/.micro-eval-server/workspaces/<workspace-id>/`. Each workspace:

- Has its own `eval.yaml`, `tasks/`, and `.micro-eval/runs/`
- Acts as a `project_root` for ExecutionKernel — cell-level worktree isolation works identically inside it
- Is owned by a member (recorded at creation, immutable)
- Has its own trend index (`index.db`)

This means there are **two layers** of workspace isolation in server mode:

| Layer | Scope | Mechanism |
|-------|-------|-----------|
| Server workspace | Per-member evaluation environment | Directory isolation under `~/.micro-eval-server/workspaces/` |
| Cell workspace | Per-cell execution sandbox | Git worktree / blank / files under `.micro-eval/workspaces/<run>/<cell>/` |

API routes enforce workspace boundaries: a request to `/api/workspaces/[id]/runs/...` can only access runs within that workspace. Path traversal attempts are rejected by format validation and containment checks.

## Next Steps

- [Trend Analysis](/guide/trend-analysis) — track evaluation results over time, detect regressions, and annotate drift breakpoints
