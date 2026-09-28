---
title: micro-eval 用户 run 安全规范
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-07-02T18:08+08:00
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

# micro-eval 用户 run 安全规范

本文件约束用户使用 `micro-eval` 测试自己的 agent/skill 时，产品必须支持、记录或提示的安全边界。

## Secrets

- MVP secrets 来源仅为环境变量。
- 只有 Configuration 声明需要的 secrets 才注入 agent env。
- secrets value 只在内存中用于 redaction。
- stdout / stderr / text artifacts 持久化前必须 redacted。
- binary artifact 无法 redaction 时必须记录 warning。
- EvidenceItem.summary 不得包含原始 secret 值。

## Workspace

- agent 只在分配的 workspace 中执行。
- 分配的 workspace 必须创建在当前 eval project 的 `.micro-eval/workspaces/{run_id}/{cell_id}/` 下；不得未经用户明确配置让 agent cwd 落到系统临时目录或项目外目录。
- project-local workspace / worktree 生命周期由 Environment Layer 管理。
- cleanup 失败要记录，不要静默。
- 不允许 adapter 任意写宿主项目根目录。
- 用户应优先使用一次性 workspace 或受控 git worktree 运行不可信 agent。

## Multi-turn Subprocess (Conversational Evaluation)

- SubprocessBridge keeps the agent process alive for the duration of a multi-turn conversation (unlike single-turn where the process exits after one invocation). This extends the I/O exposure window.
- `turn_timeout_s` (per-turn) and `max_turns` (total turns) are mandatory configuration for conversational evaluation. Defaults: turn_timeout_s=60, max_turns=10.
- Bridge shutdown must use graceful sequence: close stdin → wait(5s) → SIGTERM → wait(1s) → SIGKILL. This is enforced in `SubprocessBridge.stop()`.
- All stdout output from every turn must pass through `Redactor` before being stored in conversation log or evidence.
- If the agent process exits unexpectedly mid-conversation, the bridge must raise `BridgeError` (not silently continue with stale data).
- Zombie process risk: if `stop()` is not called (e.g., due to unhandled exception in the caller), the subprocess may linger. The execution kernel must ensure `stop()` is called in a `finally` block.

## Network and External Services

- **Level 0（默认，`logical`）**：不实现任何网络隔离。agent 与宿主机拥有相同的网络访问能力。如果 agent 需要外部服务，这属于当前环境事实，必须进入 caveat 或 snapshot context。
- **Level 1（`os_policy`，可选，v0.3.0）**：macOS Seatbelt（`sandbox-exec`）与 Linux Bubblewrap（`bwrap`）provider 支持按 `network_policy` 字段做进程级网络限制，但两者的实际强制能力不完全等价，措辞不得夸大：
  - `network_policy=full`：两个 provider 均放行全部网络访问，等同 Level 0 的网络行为。
  - `network_policy=none`：Seatbelt 生成的 sandbox profile 拒绝全部 `network*` 操作；Bubblewrap 使用 `--unshare-net` 移除整个网络命名空间。两者均为**阻断式拒绝**，而非细粒度过滤。
  - `network_policy=allowlist`：**不是真正意义上的域名/地址白名单**。Seatbelt 会在 deny 规则前插入一条 `(allow network* (remote ip "localhost:*"))`，实际效果是"仅放行 localhost，其余全部拒绝"；Bubblewrap 对 `allowlist` 与 `none` 采取完全相同的处理（同样是 `--unshare-net` 整体断网），**不做任何按地址的放行**。也就是说在 Linux 上配置 `allowlist` 目前等价于 `none`。
  - 文件系统侧：两个 provider 允许读取系统路径（Seatbelt `allow file-read*`；Bubblewrap 只读绑定 `/usr` `/bin` `/lib` `/lib64` `/etc`），写入被限制在 workspace 目录内。这是进程级 OS 策略隔离，不是容器或虚拟机级别的强隔离。
  - **降级行为**：当 task 请求 `isolation_level=os_policy` 但当前平台不满足 provider 可用性（找不到 `sandbox-exec` / `bwrap` 二进制、或非 macOS/Linux）时，`WorkspaceManager` 会静默降级为 Level 0（`logical`，无隔离）并追加 caveat，而不是 fail-hard。使用 Level 1 时应确认 caveat 是否触发了降级。
- **远程 provider（E2B/Modal，可选）**：E2B 提供 VM 级隔离（`isolation_level=vm`），Modal 提供容器级隔离（`isolation_level=container`），均需通过 `MICRO_EVAL_SECRET_*` 声明凭据。与 Level 1 不同，缺少凭据或 SDK 时这两个 provider **fail-hard**（抛出 `WorkspaceProviderError`），不会静默降级为 Level 0。
- Langfuse / DeepEval / LLM judge 是未来或可选能力，不得成为 MVP run 成功的必要条件。
- 用户不应把高权限网络凭据默认暴露给被评测 agent；即便配置了 Level 1/远程 provider，也不应把网络限制当作可以放心暴露高权限凭据的理由。

## Artifacts and Evidence

- raw artifact 访问必须受 run/artifact manifest 边界约束。
- symlink、hardlink、binary、oversized、路径穿越等 artifact 风险必须被拒绝、降级或显式记录 warning。
- 用户看到的比较结论必须可追溯到 task、config、snapshot、evidence 和 artifact ref。

## Decision Safety

- snapshot mismatch 不得产生强 winner / regression 结论。
- 对不可比或证据不足的结果，应降级为 `not_comparable` 或 `inconclusive`。
- 安全 caveat 应进入报告或 UI，而不是只记录在内部日志。
