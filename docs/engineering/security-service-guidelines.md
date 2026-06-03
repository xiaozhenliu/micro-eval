---
title: micro-eval 产品/服务安全规范
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-06-03T09:28+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - service
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/frontend-guidelines.md
  - docs/releases/
---

# micro-eval 产品/服务安全规范

本文件约束 `micro-eval` 作为产品表面对用户暴露的安全边界，包括 CLI、本地 UI/API、静态报告、发布包，以及未来可能的服务化形态。

## 当前 MVP 服务边界

- MVP 是 local-first 工具，不提供多团队协作、RBAC/SSO、复杂审计或托管服务能力。
- 本地 UI/API 只应读取当前项目允许的 `.micro-eval/` run 数据和 manifest-bound artifact。
- 报告和 UI 不得直接暴露未经过 manifest/ref 边界校验的 raw filesystem path。
- 发布包不得依赖 dev-only 文档或运行时私有资料。

## UI/API 与报告暴露

- API route 必须验证 run/artifact 边界，不能把任意路径作为文件读取入口。
- artifact 内容只通过明确的 `artifact_id` / manifest ref 暴露。
- text/html 报告必须避免注入风险；渲染用户/agent 输出时必须转义或使用安全模板策略。
- UI/Decision 面向用户展示 caveat，而不是隐藏安全降级。

## 发布与分支边界

- `main` 发布分支不得跟踪 `docs/superpowers/`、`docs/_archive/`、`docs/references/`、BRD、PRD。
- 发布 evidence 必须记录安全相关验证结果。
- 发布脚本生成的 `AGENTS.md` / `CLAUDE.md` 只能提供 main 分支必要 guardrails，不应泄露 dev-only 内容。

## 未来服务化边界

如果 `micro-eval` 从本地工具演进为托管服务，必须先补充新的服务安全规范，至少覆盖：

- authentication / authorization；
- tenant isolation；
- audit logging；
- hosted sandbox / network isolation；
- secret storage and rotation；
- data retention and deletion；
- abuse prevention and rate limiting。
