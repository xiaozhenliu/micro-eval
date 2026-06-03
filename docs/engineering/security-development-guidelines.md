---
title: micro-eval 开发实施安全规范
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-06-03T09:28+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - development
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/python-guidelines.md
  - docs/engineering/frontend-guidelines.md
  - docs/engineering/testing-guidelines.md
---

# micro-eval 开发实施安全规范

本文件约束开发者和 agent 修改 `micro-eval` 自身代码时必须遵守的安全实现要求。

## Subprocess and Shell

- trusted execution path 不得使用 shell interpolation。
- subprocess 调用必须使用 argv-only 形式。
- 用户输入、task input、expected output、agent command 不得拼接成 shell 字符串执行。

## Env and Secret Handling

- host env 继承必须 allowlist。
- secrets 注入必须以 Configuration 声明为边界。
- 任何会持久化或返回给 UI/API 的文本证据都必须先 redaction。
- 新增 evidence、artifact、report、UI/API 输出路径时，必须重新检查 secret 泄漏风险。

## Workspace and Artifact Handling

- agent cwd 必须是分配的 workspace。
- adapter / runner 不得写出 workspace 和 run artifact 边界。
- artifact 暴露给 UI/API 前必须经过 manifest/ref 边界。
- symlink、hardlink、binary、oversized、路径穿越等 artifact 风险必须被拒绝、降级或显式记录 warning。

## Decision Safety

- 任何影响 comparability 的信号都必须进入 snapshot / caveat / decision evidence。
- snapshot mismatch、缺失 evidence、artifact 不可信时，不得产生强结论。

## Verification and Review

涉及实现改动时至少检查：

- 是否引入 shell interpolation？
- 是否可能泄露 secrets？
- 是否绕过 workspace 边界？
- 是否把 raw artifact 直接暴露给 Decision / UI？
- 是否让 snapshot mismatch 仍能产生强结论？
- 是否缺少否定测试或等价的安全验证？

交付报告中必须说明：

- secrets redaction 如何处理；
- workspace boundary 如何处理；
- shell interpolation 如何避免。
