---
title: "micro-eval 测试工程规范"
date: 2026-06-02
status: draft
type: engineering-guidelines
tags:
  - engineering
  - testing
  - micro-eval
---

# micro-eval 测试工程规范

测试架构的权威来源是 `docs/superpowers/specs/2026-06-02-test-architecture.md`。本文档只补工程执行原则。

## Test Types

- Unit：纯函数、schema、ID、digest、redaction。
- Contract：Pydantic 与 zod parity；golden JSON。
- Integration：Kernel + Adapter + Workspace + Store。
- E2E：CLI `run` -> result files -> `report`。
- UI：API route、ResultMatrix、ArtifactViewer、EvaluationPanel。

## What Must Be Tested

每个 Must not bypass 都要有否定测试。

最低测试清单：

- shell 字符串插值被拒绝。
- Kernel 通过 Adapter 调用 agent。
- EvaluationResult 必须引用 EvidenceItem。
- DecisionStatus 强结论必须引用 evaluation / evidence。
- snapshot mismatch 降级结论。
- secrets 不出现在 artifacts、evidence、report、UI response。
- Pydantic / zod schema 对齐。

## No Flaky Tests

- 常规测试不调用真实 LLM。
- 常规测试不依赖外网。
- subprocess 使用 mock agent / fixture script。
- git workspace 测试使用小型 fixture repo。
- 时间与随机数要可控。

