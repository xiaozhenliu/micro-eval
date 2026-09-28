---
title: micro-eval User Run Security Guidelines
language: en
authoritative: true
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-09-27T16:00+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - user-runs
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/security-development-guidelines.md
---

# micro-eval User Run Security Guidelines

This file constrains the security boundaries the product must support, record, or surface when users test their own agents/skills with `micro-eval`.

## Secrets

- In the MVP, secrets come only from environment variables.
- Only secrets a Configuration declares as needed are injected into the agent env.
- Secret values exist in memory only for redaction.
- stdout / stderr / text artifacts must be redacted before persistence.
- Binary artifacts that cannot be redacted must record a warning.
- Complete binary artifacts within the limits remain available with `redacted: false` and `binary_redaction_skipped`; do not silently delete them or claim their bytes were sanitized.
- EvidenceItem summaries never contain raw secret values.

## Workspace

- Agents execute only inside the assigned workspace.
- Local assigned workspaces are created under the current eval project's `.micro-eval/workspaces/{run_id}/{cell_id}/`. Selecting a remote provider explicitly places the agent cwd in the cell's remote sandbox; remote paths must never be passed to a local subprocess.
- The Environment layer owns the lifecycle of project-local workspaces / worktrees.
- Cleanup failures are recorded, never silent.
- Adapters may not freely write to the host project root.
- Users should prefer disposable workspaces or controlled git worktrees when running untrusted agents.

## Multi-turn Subprocess (Conversational Evaluation)

- Conversational execution currently supports only `logical`. Its execution context opens a provider-owned persistent interactive bridge, separate from single-turn command execution. Reject any non-logical isolation request before preparing a workspace because those providers do not support the bridge.

- SubprocessBridge keeps the agent process alive for the duration of a multi-turn conversation (unlike single-turn where the process exits after one invocation). This extends the I/O exposure window.
- `turn_timeout_s` (per-turn) and `max_turns` (total turns) are mandatory configuration for conversational evaluation. Defaults: turn_timeout_s=60, max_turns=10.
- Bridge shutdown must use graceful sequence: close stdin → wait(5s) → SIGTERM → wait(1s) → SIGKILL. This is enforced in `SubprocessBridge.stop()`.
- The bridge owns a local process group and applies group termination on shutdown, including after its leader exits. Descendants that leave the group remain outside this cleanup guarantee.
- All stdout output from every turn must pass through `Redactor` before being stored in conversation log or evidence.
- If the agent process exits unexpectedly mid-conversation, the bridge must raise `BridgeError` (not silently continue with stale data).
- Zombie process risk: if `stop()` is not called (e.g., due to unhandled exception in the caller), the subprocess may linger. The execution kernel must ensure `stop()` is called in a `finally` block.

## Network and External Services

- **Cell execution ownership**: a prepared workspace owns one execution context and provider. Setup, the single-turn agent, and command validators execute through that context. Input, output, artifact transfer, observation, and cleanup remain bound to the same cell; a remote path must never be used as a host cwd.
- **Level 0 (default, `logical`)**: no OS filesystem or network isolation is implemented. The agent has the host user's permissions. Network policy intent must not be described as enforcement at this level.
- **Level 1 (`os_policy`)**: Seatbelt (`sandbox-exec`) on macOS and Bubblewrap (`bwrap`) on Linux wrap setup, the single-turn agent, and command validators.
  - `network_policy=full` permits network access; `none` denies network operations with Seatbelt and uses an isolated network namespace with Bubblewrap.
  - `network_policy=allowlist` is rejected. There are no explicit allowlist rules, so this value must not be treated as localhost access, `none`, or a domain filter.
  - Host writes are limited to the current workspace and its dedicated output staging directory. The run metadata directory and sibling cell workspaces must not be writable. Narrow device exceptions and private runtime mounts are not host data write grants.
  - Seatbelt permits broad host reads. Bubblewrap exposes read-only system, runtime, and project roots so configured binaries can start. Neither provider establishes a confidentiality boundary for readable host files.
  - If no OS provider is available before selection, `WorkspaceManager` degrades to `logical` and records a caveat. After selection, policy, wrapper startup, or command failures fail the cell without an unsandboxed retry.
- **Remote providers**: E2B (`vm`) and Modal (`container`) create one sandbox per cell and retain it for setup, the single-turn agent, and command validators. Inputs and outputs use provider-owned bounded transfer, with relative-path checks and rejection of links and special files. SDKs and provider credentials are required; no local fallback is allowed.
  - `full` and `none` are applied at sandbox creation; the default is `none`. Record requested and effective network policy separately. Reject `allowlist` until explicit rules are implemented.
  - Provider control credentials stay in the host environment. Remote commands reject their names and values, even when listed in agent `required_secrets`.
  - Remote git observation is currently unavailable. Record `observation_unavailable` and a caveat; do not fabricate a verified same start or an empty agent diff. Local post-agent observation is captured before validators.
  - Offline contract tests verify SDK calls against the supported API shapes. They do not prove live cloud isolation, network enforcement, or cleanup. Optional credentialed live tests must be reported separately from offline results.
- **Local timeout and cancellation**: the shared runner starts a new session for local single-turn commands, sends `SIGTERM` to the process group, then `SIGKILL` after a grace period. This covers descendants that remain in that group; descendants that deliberately leave it are not guaranteed to be cleaned up.
- **Remote timeout and cancellation**: explicitly terminate the cell sandbox rather than relying only on an SDK wait timeout or sandbox TTL. Normal finalization also cleans up the sandbox. Termination/cleanup errors must be recorded; a failed termination call is not proof that all descendants stopped.
- Langfuse / DeepEval / LLM judges are future or optional capabilities and must never be required for an MVP run to succeed.
- Users should not expose high-privilege network credentials to evaluated agents by default. Network restrictions do not make credential exposure safe.

## Artifacts and Evidence

- Raw artifact access is bounded by the run/artifact manifest boundary.
- Provider output is received in a temporary directory, text is redacted before export, and only output-mode-selected artifacts enter the durable run directory. Oversized artifact bodies are omitted; a text summary may retain a bounded, redacted prefix.
- Symlink, hardlink, binary, oversized, and path-traversal artifact risks must be rejected, degraded, or explicitly recorded as warnings.
- Comparison conclusions shown to users must be traceable to tasks, configs, snapshots, evidence, and artifact refs.

## Decision Safety

- A snapshot mismatch must not produce a strong winner / regression conclusion.
- Non-comparable or evidence-starved results degrade to `not_comparable` or `inconclusive`.
- Security caveats reach the report or UI, not just internal logs.
