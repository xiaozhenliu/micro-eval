---
title: "micro-eval 安全工程规范"
date: 2026-06-02
status: draft
type: engineering-guidelines
tags:
  - engineering
  - security
  - micro-eval
---

# micro-eval 安全工程规范

安全边界从 MVP 第一版就要进入代码。

## Secrets

- MVP secrets 来源仅为环境变量。
- 只有 Configuration 声明需要的 secrets 才注入 agent env。
- secrets value 只在内存中用于 redaction。
- stdout / stderr / text artifacts 持久化前必须 redacted。
- binary artifact 无法 redaction 时必须记录 warning。
- EvidenceItem.summary 不得包含原始 secret 值。

## Filesystem and Workspace

- agent 只在分配的 workspace 中执行。
- worktree / temp dir 生命周期由 Environment Layer 管理。
- cleanup 失败要记录，不要静默。
- 不允许 adapter 任意写宿主项目根目录。

## Network and External Services

- MVP 不实现网络隔离。
- 如果 agent 需要外部服务，这属于当前环境事实，必须进入 caveat 或 snapshot context。
- Langfuse / DeepEval / LLM judge 是未来或可选能力，不得成为 MVP run 成功的必要条件。

## Code Review Checklist

涉及安全边界的改动至少检查：

- 是否引入 shell interpolation？
- 是否可能泄露 secrets？
- 是否绕过 workspace 边界？
- 是否把 raw artifact 直接暴露给 Decision / UI？
- 是否让 snapshot mismatch 仍能产生强结论？
- 是否缺少否定测试？

