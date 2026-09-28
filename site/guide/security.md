# Security Model

micro-eval executes agent commands through the workspace provider selected for each cell. This page explains the trust model, the protections in place, and the limitations you need to understand before running evaluations with untrusted agents or tasks.

::: danger Review before you run
With the default `logical` isolation, configured commands run locally under your user account and can access anything that account can access. Review task definitions, workspace types, and agent commands before running an evaluation — especially if the task prompts or agent binaries come from a source you do not control. Check the effective provider and run caveats when selecting stronger isolation.
:::

---

## argv-Only Subprocess Execution

Agent and validation commands use an **argv list**. Local providers and Modal execute that list directly; E2B serializes it with shell quoting at its SDK boundary. Shell metacharacters in task prompts or agent output — backticks, semicolons, pipes, `$()` expansions — remain literal argument data. An explicitly configured shell command still has its normal shell semantics.

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

The prompt text is passed to the agent process as a command-line argument or via stdin, depending on the agent's `input_mode`. Its content does not trigger shell expansion.

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

micro-eval redacts declared secret values in captured text before persistence. For adapter stdout, stderr, and text artifacts, this includes secrets of any non-empty length: a whole-string match becomes exactly `[REDACTED:NAME]`, and longer values take priority when substring matches overlap. Binary artifacts containing a NUL byte are not text-redacted and must be treated separately.

Redacted output looks like:

```
Calling OpenAI API with key [REDACTED:MICRO_EVAL_SECRET_OPENAI_API_KEY]
```

Keep secrets out of `eval.yaml` and task files. Text redaction protects run results and text artifacts, but it cannot sanitize binary bytes or data an agent sends to an external service.

::: tip What gets scanned
Redaction runs on: subprocess stdout, subprocess stderr, `file_exists` artifact content, `command` expectation output, LLM judge inputs/outputs, and any human annotation text stored via the UI. The scan is value-based — it matches the actual secret string, not just the key name.
:::

---

## Workspace Boundary

Each evaluation cell runs in its assigned workspace directory. The agent process's working directory (`cwd`) is set to this cell workspace. Local providers use a directory under the project; remote providers use the cell's remote filesystem.

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
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | `full` or `none` on cell commands | Host writes limited to the cell workspace and its output staging directory; readable host files remain exposed | Reviewed agents that need local tools |
| `container` | Modal | `full` or `none` on the remote sandbox | One remote container per cell | Agents that need a remote environment |
| `vm` | E2B | `full` or `none` on the remote sandbox | One remote VM per cell | Agents that need a remote environment |

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

Single-turn setup, agent execution, and command expectations use the same cell execution context and selected provider. OS policy wrappers apply to all three; remote providers run all three in the same sandbox. Artifact transfer goes through that provider's filesystem boundary. Multi-turn conversations currently require `logical`; another isolation level is rejected before workspace preparation.

::: warning Boundaries that remain
OS policy isolation restricts host writes but does not protect secrets in readable host files. Timeout and cancellation send TERM, then KILL, to the local process group; descendants that leave that group are outside this cleanup guarantee. Remote timeout and cancellation explicitly terminate the cell sandbox, and cleanup failures remain visible in the result. Offline SDK contract tests check API calls, not the cloud service's containment or cleanup behavior; live verification needs provider credentials.
:::

`allowlist` is rejected by OS and remote providers because explicit allowlist rules are not implemented. It must not be interpreted as `none` or as an active domain filter. `logical` does not enforce a network policy.

### OS Policy Sandbox Degradation

If `os_policy` is configured but the platform does not support it (e.g., Seatbelt not available, Bubblewrap not installed), micro-eval **degrades to `logical` isolation** and adds a caveat to the run result:

```text
requested isolation os_policy unavailable on Linux; ran at logical
```

Check for caveats in `run.json` before treating results as comparable across runs with different effective isolation levels. After an OS provider is selected, a wrapper launch, policy, or command failure fails the cell; it does not retry outside the sandbox.

Remote providers (`e2b`, `modal`) do **not** degrade — if the provider is unavailable or credentials are missing, the run fails immediately. Their requested and effective network policies are recorded separately. Remote git observation is currently unavailable and is recorded as a caveat, not evidence of a verified same start.

---

## Protected Test Boundaries

The `starter-tasks` template uses the installed `micro_eval.tools.verify_protected` module to check the protected `tests/` digest before and after running a read-only temporary test copy. The verifier is outside the agent-writable fixture, so editing the fixture's tests or adding test files is rejected at those checks.

The tested module and the tests still share a Python process. Import-time code can interfere with the test runner or files it can access; the digest gate is not an adversarial isolation boundary. A pass means the protected tests passed and matched the expected digest at the checks. Keep the workspace evidence for review and select a suitable workspace provider.

---

## Artifact Safety

Artifacts collected from agent runs pass through several safety checks before being stored:

**Binary detection** — files containing NUL bytes are flagged as binary. Complete binary artifacts within the limits are retained with `redacted: false` and a `binary_redaction_skipped` warning; they are not rendered as text or included in text summaries. Do not assume their bytes have been sanitized.

**Size caps** — `guardrails.output_cap_bytes` defaults to **10 MiB** and bounds each captured stdout/stderr stream and selected output. `guardrails.artifact_cap_bytes` defaults to **50 MiB** and limits artifact persistence. Oversized artifact bodies are omitted; a text output summary may retain a bounded, redacted prefix. Truncation or omission is recorded explicitly.

**Staged publication** — provider output first enters a temporary receiving directory. Text is redacted there, and only artifacts selected by the configured output mode are exported to the durable run directory. Unselected raw files are not published as run artifacts.

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

## Team Server Security Model

When using `micro-eval serve`, the attack surface expands from "local process reads local files" to "network-reachable HTTP server." The server operates under a **trusted intranet assumption** — all team members are trusted, but the network path must still be defended against cross-origin attacks.

### CSRF Protection (4 Layers)

All write API routes (`POST`/`PUT`/`PATCH`/`DELETE`) enforce:

1. **Content-Type** — only `application/json` is accepted. Rejects `form-urlencoded`, `multipart/form-data`, `text/plain` — blocking browser `<form>` and `sendBeacon()` cross-site submissions.
2. **Custom header** — `X-Micro-Eval-Member` is required. Browsers cannot send custom headers in cross-origin simple requests without a CORS preflight.
3. **No CORS headers** — the server never returns `Access-Control-Allow-Origin`, so preflight requests from other origins are rejected by the browser.
4. **Host header allowlist** — requests with unknown `Host` values are rejected, preventing DNS rebinding attacks.

### Path Traversal Protection

All workspace and artifact access goes through ID-based lookup with containment validation:
- Workspace IDs must match `ws-<timestamp>-<hex>` format
- Resolved paths must stay inside `~/.micro-eval-server/workspaces/`
- Symlinks are resolved and re-checked for containment

### Config Override Whitelist

Enqueue requests reject `config_overrides`. Edit the workspace configuration first, then preview the resulting plan before submitting it. The admission digest binds the queued plan to that preview; changed configuration or workspace inputs require another preview.

::: warning Intranet only
The team server has no authentication layer. Do not expose it to the public internet. The `X-Micro-Eval-Member` header is self-reported and not verified — it provides attribution, not access control.
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
