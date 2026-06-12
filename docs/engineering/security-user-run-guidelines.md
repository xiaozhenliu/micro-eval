---
title: micro-eval 用户 run 安全规范
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-06-03T18:08+08:00
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

## Network and External Services

- MVP 不实现网络隔离。
- 如果 agent 需要外部服务，这属于当前环境事实，必须进入 caveat 或 snapshot context。
- Langfuse / DeepEval / LLM judge 是未来或可选能力，不得成为 MVP run 成功的必要条件。
- 用户不应把高权限网络凭据默认暴露给被评测 agent。

## Artifacts and Evidence

- raw artifact 访问必须受 run/artifact manifest 边界约束。
- symlink、hardlink、binary、oversized、路径穿越等 artifact 风险必须被拒绝、降级或显式记录 warning。
- 用户看到的比较结论必须可追溯到 task、config、snapshot、evidence 和 artifact ref。

## Decision Safety

- snapshot mismatch 不得产生强 winner / regression 结论。
- 对不可比或证据不足的结果，应降级为 `not_comparable` 或 `inconclusive`。
- 安全 caveat 应进入报告或 UI，而不是只记录在内部日志。
