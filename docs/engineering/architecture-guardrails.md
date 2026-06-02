---
title: "micro-eval 架构落地边界"
date: 2026-06-02
status: draft
type: engineering-guidelines
tags:
  - engineering
  - architecture
  - micro-eval
---

# micro-eval 架构落地边界

本文档把 Unicorn 架构不变量转成工程实现边界。架构事实以 `docs/superpowers/specs/2026-06-02-unicorn-design.md` Part I 为准。

## 决策闭环

实现代码必须服务 Unicorn 的决策闭环：

```text
Task Authoring -> Evaluation Contract -> Command Adapter -> Same-start
  -> Run (Tasks x Configurations x Repetitions) -> Evidence Chain
  -> Basic Honest Stats -> Decision Report
```

只要闭环断掉，产品就退回“展示一堆结果让用户自己猜”。那不是 micro-eval。

## 不可破坏的工程边界

| 边界 | 工程含义 |
|---|---|
| MVP is a Profile, not a fork | MVP 可以低配实现，但不能创建一套与 Unicorn 不兼容的数据模型。 |
| Run = Tasks x Configurations x Repetitions | baseline / candidate 只是 role，不能作为核心对象结构。 |
| Agent is a black box behind adapters | Execution Kernel 不知道具体 agent 的命令细节，只调用 Adapter 契约。 |
| Environment is part of input | workspace / commit / config / toolchain 等进入 snapshot 或 replay identity。 |
| Evidence before decision | Decision 只能引用 Evaluation + Evidence，不能直接解释裸 stdout。 |
| Deterministic checks before LLM judgment | test / lint / exit code / schema 能判断时，不先交给 LLM judge。 |
| Secrets are never evidence | secrets 不进入 artifacts、trace、judge prompt、report、UI response。 |
| Stable IDs + schema_version are mandatory | 跨模块对象必须有稳定 ID 和 schema version。 |

实现中如果想绕过这些边界，先改 Unicorn / MVP Profile，而不是在代码里偷偷开例外。

## 依赖方向

- Configuration 读 Asset。
- Execution 读 RunPlan。
- Agent Adapter 与 Environment 服务 Execution。
- Artifact / Trace 记录事实。
- Evaluation 读 Evidence 打分。
- Decision 读 Evaluation + Evidence 出结论。
- UI 属于 Decision Layer 的展示，不直接解释裸 stdout。

## 禁止的捷径

- UI 直接从 stdout 推断 winner。
- Kernel 直接创建 verdict。
- Adapter 决定任务是否 pass。
- Scorer 创建 workspace。
- Route Handler 绕过 RunStore 拼路径读写结果。
- legacy baseline/candidate 模型继续扩张为新功能基础。

