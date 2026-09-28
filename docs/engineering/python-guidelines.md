---
title: "micro-eval Python 工程规范"
date: 2026-06-02
status: draft
type: engineering-guidelines
tags:
  - engineering
  - python
  - micro-eval
---

# micro-eval Python 工程规范

适用范围：`src/micro_eval/` 与 Python tests。

## Language and Runtime

- Python 版本：3.11+。
- 包管理：优先 `uv`。
- CLI：Typer。
- 数据模型：Pydantic v2。
- 输出格式：CLI 面向人类时可用 Rich；机器输出必须是结构化 JSON。

## Code Style

- 函数签名必须有类型标注。
- 模块内部可使用 dataclass / Pydantic model，但跨模块 JSON 优先 Pydantic model。
- 路径使用 `pathlib.Path`。
- 时间戳使用明确格式；进入 ID 的 timestamp 使用 compact 格式，避免与 `::` 冲突。
- 错误类型要可区分，例如 config error、adapter error、workspace error、store error。
- 代码注释必须使用英文。

避免：

- 用裸 dict 在多个模块间传递领域对象。
- 在业务代码中拼接 `.micro-eval/runs/...`。
- 直接调用 `asyncio.create_subprocess_shell`。
- 用 display name 当 stable ID。
- 捕获宽泛异常后吞掉错误。

## Async and Subprocess

- agent 执行是 I/O bound，使用 asyncio。
- 并发必须受 `max_concurrency` 控制。
- 每个 RunCell 的 timeout 单独处理。
- 超时后先终止，再升级 kill。
- 单个 cell 失败不能阻断其他 cell，除非 RunPlan 的 guardrail 明确要求停止。

## Safe Subprocess Checklist

任何新增 subprocess 调用都要回答：

- 输入从哪里来？
- 是否经过 shell？
- stdout / stderr 是否有大小上限？
- secrets 是否可能泄露？
- 超时后如何终止子进程？
- 失败是否会影响其他 cell？

默认要求：

- 使用 argv list。
- 禁止 shell 字符串插值。
- task input 通过 stdin 或文件传递。
- output file / directory 通过明确环境变量或参数声明。
- timeout、output cap、artifact size cap 必须从 guardrails 读取或使用默认值。
- stdout / stderr 持久化前必须走 redaction。

## Pydantic Models

- 所有跨模块对象携带 `schema_version`。
- enum 使用明确字符串，不使用隐式 bool 表达复杂状态。
- Optional 字段必须有明确语义：unknown、not applicable、not collected 不能混淆。
- digest 字段必须说明输入材料与 canonicalization 规则所在文档。
- model 序列化结果必须进入 contract tests。

