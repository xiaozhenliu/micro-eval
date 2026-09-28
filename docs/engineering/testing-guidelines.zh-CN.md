---
title: "micro-eval 测试工程规范"
language: zh-CN
agent_read: false
authoritative: docs/engineering/testing-guidelines.md
date: 2026-06-02
updated_at: 2026-09-27T16:00+08:00
status: draft
type: engineering-guidelines
tags:
  - engineering
  - testing
  - micro-eval
---

# micro-eval 测试工程规范

> **翻译参考，非权威版本。** 本文件是 [testing-guidelines.md](testing-guidelines.md) 的中文翻译，仅供人类阅读。
> 规范以英文原版为准；两者不一致时一律以英文版为准。Agent 与自动化流程必须阅读英文原版，不要读取本文件。

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
