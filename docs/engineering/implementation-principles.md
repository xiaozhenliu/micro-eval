---
title: "micro-eval 实施原则"
date: 2026-06-02
status: draft
type: engineering-guidelines
tags:
  - engineering
  - implementation
  - micro-eval
---

# micro-eval 实施原则

本文档定义代码实现时的通用取舍。字段、模块契约、MVP 范围以 Unicorn 和 MVP Profile 为准。

## Schema First

跨模块对象先定义 schema，再写业务流程。

- Python 端使用 Pydantic v2。
- TypeScript 端使用 zod。
- 同一对象的字段名、enum、可空性、默认值必须对齐。
- 新增或修改跨语言 JSON 时，必须补 contract test。
- legacy schema 只能显式标记为 legacy，不能伪装成 canonical schema。

不要让 UI 根据“碰巧存在的 JSON 字段”推断语义。UI 只能消费 schema 承认的结构。

## Boundary First

先定义模块接口，再填实现。

- Configuration Layer 产出 RunPlan。
- Execution Kernel 消费 RunPlan，产出事实型 execution result。
- Agent Adapter 负责命令调用与 I/O 规范化。
- Environment Layer 负责 workspace 与 snapshot。
- Artifact / Trace Layer 保存 raw artifacts 与结构化 evidence。
- Evaluation Layer 产出评分和验证结果。
- Decision Layer 产出结论、caveats、recommended action。

## Store Behind Interfaces

数据读写必须通过 store 抽象，不能把 `.micro-eval/` 路径散落在业务逻辑里。

最低要求：

- Python 侧通过 RunStore / ArtifactStore 风格接口读写 run、cell、artifact、evaluation。
- UI/API 侧通过统一数据访问层读取 RunStore 暴露的数据。
- 文件路径通过注入的 base path 或 project root 计算。
- JSON 文件是 MVP 存储实现，不是业务模块的直接依赖。

这样未来从 JSON 迁移到 SQLite / hosted backend 时，不需要重写 Decision、UI、Evaluation 等层。

## Snapshot and Replay Are Inputs

可比性不是报告阶段的装饰，它是输入合同的一部分。

- branch / tag 必须在 run 开始时解析为 commit hash。
- timestamp、临时 workspace path 这类观察元数据不得进入 replay digest。
- dirty state、config hash、task revision、configuration digest 必须可追溯。
- SnapshotGateResult 必须持久化，Decision Layer 必须消费它。
- 缺关键 snapshot 时，只能输出 weak / inconclusive / not_comparable 类结论。

## Evidence Is Structured

artifact 是事实材料，EvidenceItem 是可引用证据。二者不能混用。

- stdout、stderr、diff、文件输出是 ArtifactRef。
- validation、score、annotation、snapshot gate 是 EvidenceItem。
- EvaluationResult 引用 evidence id。
- DecisionReport 引用 evaluation id 和 evidence id。
- evidence summary 是摘要，不是完整 artifact。

需要展示原文时，从 EvidenceItem 追到 ArtifactRef，再由 artifact viewer 展示。

## Migration Is Explicit

legacy v0.1.0 代码可以兼容，但不能继续扩大 legacy 模型。

- 新代码优先使用 canonical 术语：Task、Configuration、RunCell、EvidenceItem、DecisionStatus。
- legacy 字段只能在 adapter / loader / migration bridge 中处理。
- 兼容逻辑要有测试，且测试名中标明 legacy。
- 迁移阶段按 MVP Profile 的 P0-a / P0-b / P1 推进，不做 big-bang rewrite。

