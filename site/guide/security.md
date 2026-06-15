# Security Model

micro-eval executes agent commands on your local machine. This page explains the trust model, the protections in place, and the limitations you need to understand before running evaluations with untrusted agents or tasks.

::: danger Review before you run
micro-eval executes the commands you configure as subprocesses on your machine. An agent that writes files, calls external APIs, or modifies system state will do so under your user account. Always review task definitions, workspace types, and agent commands before running an evaluation — especially if the task prompts or agent binaries come from a source you do not control.
:::

---

## argv-Only Subprocess Execution

Every agent command and validation command in micro-eval is executed as an **argv list**, not a shell string. Shell metacharacters in task prompts or agent output — backticks, semicolons, pipes, `$()` expansions — are passed as literal data to the process and never interpreted by a shell.

**Practical implication:** the following task definition is safe even though the prompt contains a shell injection attempt:

```yaml
# tasks/untrusted-prompt.yaml
id: injection-attempt
input_payload: "Summarize this: $(rm -rf /tmp/important)"  # safe — never shell-expanded
workspace:
  type: blank

expectations:
  - type: exit_code
    value: 0
```

The prompt text is passed to the agent process as a command-line argument or via stdin, depending on the agent's `input_mode`. The shell never sees it.

::: warning Legacy string commands
If you supply a command as a plain string rather than a list, micro-eval emits a deprecation warning and passes it through a migration bridge that splits it with `shlex.split`. This code path is not in the trusted path — migrate all commands to list form:

```yaml
# Deprecated — avoid
command: "my-agent --model gpt-4"

# Correct
command: ["my-agent", "--model", "gpt-4"]
```
:::

---

## Secrets Channel

Secrets required by your agents must flow through a dedicated channel — never hardcoded in `eval.yaml` or task files.

### Naming Convention

All secrets must be prefixed with `MICRO_EVAL_SECRET_`:

```bash
export MICRO_EVAL_SECRET_OPENAI_API_KEY="sk-..."
export MICRO_EVAL_SECRET_ANTHROPIC_API_KEY="sk-ant-..."
```

### Declaring Required Secrets

Declare which secrets a configuration needs in `eval.yaml`. micro-eval validates that all declared secrets are present in the environment before starting a run:

```yaml{8-10}
configurations:
  - name: gpt-4o
    command: ["my-agent", "--model", "gpt-4o"]
    repetitions: 3
    environment:
      MODEL: "gpt-4o"
    required_secrets:
      - MICRO_EVAL_SECRET_OPENAI_API_KEY
```

Secrets are injected into the subprocess environment under their full name. The agent process receives them as standard environment variables — for example, `MICRO_EVAL_SECRET_OPENAI_API_KEY` is available directly from the environment.

### Auto-Redaction

micro-eval scans all captured text — stdout, stderr, artifact content, evidence text, and human annotation comments — and redacts any value that matches a declared secret before persisting it to disk.

Redacted output looks like:

```
Calling OpenAI API with key [REDACTED:MICRO_EVAL_SECRET_OPENAI_API_KEY]
```

Secrets are **never written** to `eval.yaml`, `run.json`, `result.json`, HTML reports, or any other artifact.

::: tip What gets scanned
Redaction runs on: subprocess stdout, subprocess stderr, `file_exists` artifact content, `command` expectation output, LLM judge inputs/outputs, and any human annotation text stored via the UI. The scan is value-based — it matches the actual secret string, not just the key name.
:::

---

## Workspace Boundary

Each evaluation cell runs inside an isolated workspace directory. The agent process's working directory (`cwd`) is set to this cell workspace, not to your host project root.

```
.micro-eval/
└── workspaces/
    └── r-20260615-001/
        └── hello__baseline__rep-1/   ← agent cwd
            └── (workspace files)
```

### Expectation Validation Scope

`file_exists` and `command` expectations are validated relative to the cell workspace directory:

```yaml
expectations:
  - type: file_exists
    path: "output/report.txt"  # resolved against workspace dir, not host root
  - type: command
    command: ["cat", "output/report.txt"]  # cwd = workspace dir
```

Paths that attempt to escape the workspace (e.g., `../../host-secret.txt`) are rejected with a boundary violation error.

### Artifact Access

Artifacts produced by agent runs are accessed through a manifest system. Every artifact is assigned an `artifact_id` at collection time, and all subsequent reads go through a boundary check that ensures the resolved path stays within the run directory:

```
artifact_id: "abc123"  →  .micro-eval/runs/{run_id}/artifacts/abc123/
```

Direct filesystem access to arbitrary paths is not exposed through the API or UI.

### Source Path Constraints

When a workspace is initialized from a `files` or `git_repo` source, the source paths are constrained to the project root. Path traversal sequences (`..`) in source paths are rejected:

```yaml
workspace:
  type: files
  source: "./fixtures/my-task"   # OK — relative to project root
  # source: "../../etc/passwd"   # Rejected — path traversal
```

---

## Isolation Levels

micro-eval supports four workspace isolation levels, selected per configuration. Stronger isolation reduces the risk that an agent can damage your host system or leak data between runs.

| Level | Provider | Network isolation | Filesystem isolation | Use when |
|---|---|---|---|---|
| `logical` | git worktree | None | Partial (cwd only) | Default; dev/test agents you trust |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | Optional (`network_policy: none`) | Yes (sandbox profile) | Untrusted agents on trusted hardware |
| `container` | Docker (future) | Yes | Yes | CI environments |
| `vm` | E2B / Modal | Yes | Yes | Untrusted agents, production evaluation |

Configure isolation in your task's `workspace` block:

::: code-group

```yaml [Logical (default)]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: logical
```

```yaml [OS Policy — macOS Seatbelt]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: main
  isolation_level: os_policy
  network_policy: none
```

```yaml [Remote VM — E2B]
workspace:
  type: blank
  isolation_level: vm
  trust_level: untrusted
  network_policy: none
```

:::

::: warning Network isolation is not provided by the local runner
The default `logical` isolation level does **not** restrict network access. An agent running under `logical` isolation can make arbitrary outbound network calls, contact external APIs, or exfiltrate data. If you are evaluating agents you did not write, use `os_policy` with `network_policy: none` or a remote VM provider. Full network isolation requires `os_policy` (partial) or `vm` (complete).
:::

### OS Policy Sandbox Degradation

If `os_policy` is configured but the platform does not support it (e.g., Seatbelt not available, Bubblewrap not installed), micro-eval **degrades to `logical` isolation** and adds a caveat to the run result:

```json
{
  "isolation_level": "logical",
  "isolation_caveat": "os_policy requested but Seatbelt/Bubblewrap unavailable; degraded to logical"
}
```

Check for caveats in `run.json` before treating results as comparable across runs with different effective isolation levels.

Remote VM providers (`e2b`, `modal`) do **not** degrade — if the provider is unavailable or credentials are missing, the run fails immediately.

---

## Artifact Safety

Artifacts collected from agent runs pass through several safety checks before being stored:

**Binary detection** — files containing NUL bytes are flagged as binary. Binary artifacts are stored but not rendered as text in the UI or included in report summaries.

**Size caps** — subprocess output (stdout/stderr combined) is capped at **10 MB**. Individual artifact files are capped at **50 MB**. Oversized output is truncated with a truncation marker appended.

**Symlink and hardlink protection** — reserved artifact paths (e.g., paths that would resolve outside the run directory) are rejected at collection time. Symlinks pointing outside the artifact boundary are not followed.

**Manifest-bound access** — the UI and report generator never construct artifact paths from user input. All access goes through `artifact_id` lookup in the run manifest, and the resolved path is checked against the run directory before the file is opened.

---

## Report Safety

HTML reports are generated with **autoescaping enabled**. Agent output, task prompts, and annotation text embedded in a report are HTML-escaped before rendering. This prevents stored XSS if a report is opened in a browser and the agent output contained HTML or JavaScript.

::: tip Self-contained reports
HTML reports embed all data inline and make no external requests when opened. They are safe to share or archive without exposing any `.micro-eval/` internals.
:::

---

## Web UI Network Boundary

The Web UI (`micro-eval ui`) runs a local Next.js server that reads `.micro-eval/` JSON files directly from the filesystem. It does not:

- Make outbound network requests
- Expose API routes to the network (binds to `localhost` only)
- Authenticate users (assume anyone who can reach the port is trusted)

::: warning Localhost binding only
The Web UI binds to `127.0.0.1` and is not intended to be exposed on a network interface. Do not run it behind a reverse proxy accessible to other machines without adding your own authentication layer.
:::

---

## Security Checklist Before Running

Use this checklist before evaluating agents or tasks from external sources:

- [ ] All agent commands are in list form (not shell strings)
- [ ] All secrets use the `MICRO_EVAL_SECRET_*` prefix and are declared in `required_secrets`
- [ ] Task `source` paths do not contain `..` traversal sequences
- [ ] Workspace type is appropriate for the task (use `git_repo` with a pinned commit for reproducibility)
- [ ] Isolation level matches your trust level (use `os_policy` or `vm` for untrusted agents)
- [ ] You have reviewed what the agent command does before executing it
- [ ] If using `os_policy`, you have verified the sandbox is actually active (check `run.json` for caveats)
- [ ] HTML reports will be opened in a browser only from runs you control
