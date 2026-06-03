---
title: micro-eval 安全规范索引
doc_type: reference
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-06-03T09:28+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - micro-eval
related:
  - docs/engineering/security-service-guidelines.md
  - docs/engineering/security-user-run-guidelines.md
  - docs/engineering/security-development-guidelines.md
---

# micro-eval 安全规范索引

安全不是单一维度。本项目把安全规范拆成三层，避免把用户运行 agent 的风险、产品服务边界、开发实现约束混在同一个文件里。

## 三层安全 source of truth

| 层级 | 读取文件 | 适用问题 |
| --- | --- | --- |
| 产品/服务安全 | `docs/engineering/security-service-guidelines.md` | `micro-eval` 作为 CLI、本地 UI/API、报告、发布包或未来服务时，产品自身应该暴露什么、不暴露什么。 |
| 用户 run 安全 | `docs/engineering/security-user-run-guidelines.md` | 用户用 `micro-eval` 测试自己的 agent/skill 时，secrets、workspace、network、artifact、caveat 应如何处理和提示。 |
| 开发实施安全 | `docs/engineering/security-development-guidelines.md` | 开发者或 agent 修改 runner、adapter、store、UI/API、report、decision、验证逻辑时必须遵守什么。 |

## 使用规则

- 开发实现前，至少读取 `security-development-guidelines.md`。
- 如果改动影响用户发起 run、workspace、secrets、artifact、network caveat 或 evidence，必须同时读取 `security-user-run-guidelines.md`。
- 如果改动影响 CLI、本地 UI/API、报告、发布包、raw artifact 访问或未来服务化边界，必须同时读取 `security-service-guidelines.md`。
- 不要在本索引重新定义具体安全规则；具体规则只写入对应层级文件。
