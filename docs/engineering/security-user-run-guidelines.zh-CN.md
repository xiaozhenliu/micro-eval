---
title: micro-eval 用户 run 安全规范
language: zh-CN
agent_read: false
authoritative: docs/engineering/security-user-run-guidelines.md
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-09-27T16:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - engineering
  - security
  - user-runs
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/security-development-guidelines.md
---

# micro-eval 用户 run 安全规范

> **翻译参考，非权威版本。** 本文件是 [security-user-run-guidelines.md](security-user-run-guidelines.md) 的中文翻译，仅供人类阅读。
> 规范以英文原版为准；两者不一致时一律以英文版为准。Agent 与自动化流程必须阅读英文原版，不要读取本文件。

本文件约束用户使用 `micro-eval` 测试自己的 agent/skill 时，产品必须支持、记录或提示的安全边界。

## Secrets

- MVP secrets 来源仅为环境变量。
- 只有 Configuration 声明需要的 secrets 才注入 agent env。
- secrets value 只在内存中用于 redaction。
- stdout / stderr / text artifacts 持久化前必须 redacted。
- binary artifact 无法 redaction 时必须记录 warning。
- 未超限的完整 binary artifact 应保留并标记 `redacted: false` 和 `binary_redaction_skipped`；不得静默删除，或声称其字节已经脱敏。
- EvidenceItem.summary 不得包含原始 secret 值。

## Workspace

- agent 只在分配的 workspace 中执行。
- 本机 workspace 必须创建在当前 eval project 的 `.micro-eval/workspaces/{run_id}/{cell_id}/` 下。显式选择远程 provider 时，agent cwd 位于该 cell 的远程沙箱中；不得将远程路径传给本机子进程。
- project-local workspace / worktree 生命周期由 Environment Layer 管理。
- cleanup 失败要记录，不要静默。
- 不允许 adapter 任意写宿主项目根目录。
- 用户应优先使用一次性 workspace 或受控 git worktree 运行不可信 agent。

## Multi-turn Subprocess (Conversational Evaluation)

- 对话执行当前仅支持 `logical`。执行上下文创建所属 provider 的持久交互 bridge，与单轮命令执行分开。其他 provider 不支持该 bridge，任何非 logical 隔离请求必须在准备工作区前被拒绝。

- SubprocessBridge keeps the agent process alive for the duration of a multi-turn conversation (unlike single-turn where the process exits after one invocation). This extends the I/O exposure window.
- `turn_timeout_s` (per-turn) and `max_turns` (total turns) are mandatory configuration for conversational evaluation. Defaults: turn_timeout_s=60, max_turns=10.
- Bridge shutdown must use graceful sequence: close stdin → wait(5s) → SIGTERM → wait(1s) → SIGKILL. This is enforced in `SubprocessBridge.stop()`.
- bridge 持有本机进程组，关闭时执行进程组终止，即使组长已退出也会清理。主动脱离该组的后代不在清理保证内。
- All stdout output from every turn must pass through `Redactor` before being stored in conversation log or evidence.
- If the agent process exits unexpectedly mid-conversation, the bridge must raise `BridgeError` (not silently continue with stale data).
- Zombie process risk: if `stop()` is not called (e.g., due to unhandled exception in the caller), the subprocess may linger. The execution kernel must ensure `stop()` is called in a `finally` block.

## Network and External Services

- **cell 执行归属**：prepared workspace 持有一个执行上下文和 provider。setup、单轮 agent 和 command validator 都通过该上下文执行。输入、输出、产物传输、observation 和 cleanup 必须绑定同一个 cell；不得把远程路径当作宿主 cwd。
- **Level 0（默认，`logical`）**：不实现 OS 文件系统或网络隔离。agent 拥有宿主用户权限，不得将该级别的网络策略意图描述为已强制执行。
- **Level 1（`os_policy`）**：macOS Seatbelt（`sandbox-exec`）和 Linux Bubblewrap（`bwrap`）包装 setup、单轮 agent 和 command validator。
  - `network_policy=full` 允许网络访问；`none` 在 Seatbelt 中拒绝网络操作，在 Bubblewrap 中使用独立网络命名空间。
  - `network_policy=allowlist` 会被拒绝。当前没有明确的允许规则，不能将其理解为 localhost 放行、`none` 或域名过滤。
  - 宿主写入仅限当前 workspace 和独立的输出 staging 目录。不得允许写入 run 元数据目录或其他 cell 工作区。狭窄的设备例外和私有运行时挂载不代表宿主数据写入授权。
  - Seatbelt 允许广泛宿主读取。Bubblewrap 暴露只读的系统、运行时和项目根目录，以便启动配置的二进制程序。两者都不构成可读宿主文件的保密边界。
  - 选择前没有可用 OS provider 时，`WorkspaceManager` 降级为 `logical` 并记录 caveat。一旦选定 provider，策略、包装器启动或命令失败都会使 cell 失败，不得在沙箱外重试。
- **远程 provider**：E2B（`vm`）和 Modal（`container`）为每个 cell 创建一个沙箱，供 setup、单轮 agent 和 command validator 复用。输入输出使用 provider 管理的有界传输，检查相对路径并拒绝链接和特殊文件。需要 SDK 与 provider 凭据，不得回退本机。
  - `full` 和 `none` 在沙箱创建时生效，默认 `none`。请求策略与实际生效策略分别记录。明确规则实现前拒绝 `allowlist`。
  - provider 控制凭据留在宿主环境中。远程命令拒绝其名称和值，即使被列入 agent 的 `required_secrets`。
  - 远程 git observation 当前不可用。必须记录 `observation_unavailable` 和 caveat，不得伪造已验证的同起点或空 agent diff。本机 agent 执行后的 observation 在 validator 之前采集。
  - 离线 contract 测试验证受支持 API 形状的 SDK 调用，不能证明 live 云端隔离、网络强制执行或清理。可选的带凭据 live 测试必须与离线结果分开报告。
- **本机超时和取消**：共享 runner 为本机单轮命令创建新 session，先向进程组发送 `SIGTERM`，宽限期后发送 `SIGKILL`。保证覆盖仍留在组内的后代；主动脱组的后代不保证被清理。
- **远程超时和取消**：显式终止该 cell 沙箱，不能仅依赖 SDK 等待超时或沙箱 TTL。正常 finalization 也清理沙箱。终止/清理错误必须记录，终止调用失败不能证明全部后代已经停止。
- Langfuse / DeepEval / LLM judge 是未来或可选能力，不得成为 MVP run 成功的必要条件。
- 用户不应将高权限网络凭据默认暴露给被评测 agent。网络限制不能使凭据暴露变得安全。

## Artifacts and Evidence

- raw artifact 访问必须受 run/artifact manifest 边界约束。
- provider 输出先进入临时接收目录，文本脱敏后再导出，只有 output mode 选中的产物进入持久化 run 目录。超额产物正文省略；文本摘要可以保留经过脱敏的有界前缀。
- symlink、hardlink、binary、oversized、路径穿越等 artifact 风险必须被拒绝、降级或显式记录 warning。
- 用户看到的比较结论必须可追溯到 task、config、snapshot、evidence 和 artifact ref。

## Decision Safety

- snapshot mismatch 不得产生强 winner / regression 结论。
- 对不可比或证据不足的结果，应降级为 `not_comparable` 或 `inconclusive`。
- 安全 caveat 应进入报告或 UI，而不是只记录在内部日志。
