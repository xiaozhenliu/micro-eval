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
tasks:
  - id: generate-readme
    prompt: "Write a README.md for a Python CLI tool called 'greet'."
    workspace:
      type: blank
```

### `files`

Copies specified files and directories into the task workspace before execution. The source paths are resolved relative to the config file.

```yaml
tasks:
  - id: refactor-utils
    prompt: "Refactor the helper functions in utils.py to reduce duplication."
    workspace:
      type: files
      sources:
        - path: src/utils.py
        - path: tests/test_utils.py
        - path: pyproject.toml
```

::: tip Fixture digests
When using `files`, micro-eval computes a SHA-256 digest of each source at run time and records them in `SameStartSnapshot.fixture_digests`. Two runs are only comparable if their fixture digests match.
:::

### `git_repo`

Creates an isolated git worktree at a specific commit. This is the most reproducible option for code-editing tasks — the agent gets a real git history, can create branches, and its changes are fully isolated from your working tree.

```yaml
tasks:
  - id: fix-issue-42
    prompt: "Fix the bug described in issue #42. The relevant code is in src/parser.py."
    workspace:
      type: git_repo
      repo: .                      # path to the repo (relative to config)
      commit: "abc1234"            # pin to a specific commit
      setup_commands:              # optional: run inside the worktree before the agent starts
        - ["uv", "sync"]
```

::: warning Pinning the commit
Always set `commit` explicitly for evaluations you intend to compare over time. If `commit` is omitted, micro-eval uses `HEAD` at run time — the workspace will drift as your repo evolves, making historical comparisons unreliable.
:::

## Isolation Levels

The `sandbox.level` field controls how tightly the agent's process is contained. Levels are defined in the provider protocol (spec §3.4.5).

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
configurations:
  - id: my-agent-v1
    agent:
      command: ["uv", "run", "my-agent"]
    sandbox:
      level: logical
```

### Level 1 — `os_policy`

Adds an OS-level sandbox policy around the agent process:

- **macOS**: Apple Seatbelt (`sandbox-exec`) restricts filesystem writes to the workspace directory
- **Linux**: Bubblewrap (`bwrap`) creates a user namespace with a private filesystem view

This level prevents an agent from accidentally (or intentionally) reading secrets from `~/.ssh`, writing to paths outside the workspace, or modifying your global config files.

```yaml
configurations:
  - id: semi-trusted-agent
    agent:
      command: ["./external-agent"]
    sandbox:
      level: os_policy
      network: allowlist              # full | allowlist | none
      network_allowlist:
        - "api.openai.com"
        - "pypi.org"
    trust: semi_trusted
```

::: warning Degradation to logical
If `os_policy` is requested but Seatbelt or Bubblewrap is not available on the host (e.g., Linux without `bwrap` installed), micro-eval **degrades to `logical`** and records a `mixed_isolation` caveat in the run result. The run is not aborted, but the caveat is surfaced in the UI and excluded from strict comparability checks.

To require `os_policy` without silent downgrade, set `sandbox.strict: true`.
:::

### Level 4 — `vm` (Remote Execution)

Runs the agent inside a remote VM provided by E2B or Modal. This is the highest isolation level and is appropriate for:

- Untrusted or adversarial agents
- Agents that need a clean Linux environment regardless of host OS
- Tasks that require specific OS packages or kernel features

```yaml
configurations:
  - id: untrusted-agent
    agent:
      command: ["./unknown-agent"]
    sandbox:
      level: vm
      provider: e2b                   # e2b | modal
      template: "base-python-3.11"    # provider-specific template ID
    trust: untrusted
    network: none
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

## Provider Registry

micro-eval selects the appropriate backend at run time through the `WorkspaceProvider` protocol and a provider registry. You do not need to configure this directly — the registry inspects the `sandbox.level` field and the host environment to pick the right backend.

| Provider | Level | Platform |
|----------|-------|----------|
| `GitWorktreeProvider` | 0 — logical | All |
| `SeatbeltProvider` | 1 — os_policy | macOS |
| `BubblewrapProvider` | 1 — os_policy | Linux |
| `E2BProvider` | 4 — vm | Any (remote) |
| `ModalProvider` | 4 — vm | Any (remote) |

## Trust Levels

The `trust` field communicates intent and is used by the provider registry to validate that the chosen isolation level is appropriate.

| Trust level | Recommended isolation | Typical use case |
|-------------|----------------------|------------------|
| `trusted` | `logical` | Your own agents, internal tools |
| `semi_trusted` | `os_policy` | Third-party agents you have reviewed |
| `untrusted` | `vm` | Downloaded agents, external contributors |
| `adversarial` | `vm` | Red-teaming, agents that may attempt escapes |

::: warning Trust is advisory, not enforced
Setting `trust: adversarial` does not automatically upgrade the isolation level. You must also set `sandbox.level: vm`. Trust is used for documentation, comparability metadata, and future policy enforcement — not as a security gate by itself.
:::

## Network Policy

The `sandbox.network` field controls outbound network access from the agent process. It applies at Level 1 and above.

| Policy | Behavior |
|--------|----------|
| `full` | No network restrictions (default for Level 0) |
| `allowlist` | Only domains listed in `network_allowlist` are reachable |
| `none` | All outbound network access blocked |

```yaml{6-10}
configurations:
  - id: offline-agent
    agent:
      command: ["./my-agent"]
    sandbox:
      level: os_policy
      network: allowlist
      network_allowlist:
        - "api.anthropic.com"
        - "raw.githubusercontent.com"
    trust: semi_trusted
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
      timeout: 120
    sandbox:
      level: logical
    trust: trusted

tasks:
  - id: add-docstrings
    prompt: "Add Google-style docstrings to every public function in src/parser.py."
    workspace:
      type: git_repo
      repo: .
      commit: "a1b2c3d"
```

```yaml [os_policy — semi-trusted agent]
configurations:
  - id: external-agent
    agent:
      command: ["./bin/external-agent", "--mode", "edit"]
      input_mode: stdin
      timeout: 180
    sandbox:
      level: os_policy
      network: allowlist
      network_allowlist:
        - "api.openai.com"
    trust: semi_trusted

tasks:
  - id: implement-feature
    prompt: "Implement the feature described in SPEC.md."
    workspace:
      type: files
      sources:
        - path: SPEC.md
        - path: src/
        - path: tests/
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
      timeout: 300
    sandbox:
      level: vm
      provider: e2b
      template: "base-python-3.11"
      strict: true
    trust: adversarial
    network: none

tasks:
  - id: code-challenge
    prompt: "Solve the algorithmic problem in challenge.txt."
    workspace:
      type: files
      sources:
        - path: challenge.txt
    expectations:
      - type: contains
        value: "SOLVED"
```

:::

## Next Steps

- [Trend Analysis](/guide/trend-analysis) — track evaluation results over time, detect regressions, and annotate drift breakpoints
