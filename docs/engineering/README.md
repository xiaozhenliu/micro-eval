---
title: micro-eval 工程规范索引
doc_type: reference
status: active
created_at: 2026-06-02T18:00+08:00
updated_at: 2026-08-29T12:39+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - micro-eval
related:
  - docs/README.md
  - docs/documentation-standard.md
---

# micro-eval 工程规范索引

本文档是工程规范入口。它负责路由，不重新定义产品目标、模块契约、字段 schema 或 MVP 范围。

## Source of Truth

不要让同一个事实拥有多个权威来源。实现前先判断要查哪份文档。

| 问题 | 权威来源 | 本目录是否可重定义 |
|---|---|---|
| 产品为什么存在、解决什么业务问题 | `micro-eval-brd.md` | 否 |
| 长期模块、架构不变量、Stable ID、证据模型 | `docs/superpowers/specs/2026-06-02-unicorn-design.md` Part I | 否 |
| MVP 当前启用哪些能力、哪些不做、迁移分期 | `docs/superpowers/specs/2026-06-02-mvp-profile.md` | 否 |
| micro-eval 自身代码如何测试 | `docs/superpowers/specs/2026-06-02-test-architecture.md` | 否 |
| 代码如何组织、实现时如何取舍、技术栈约束 | `docs/engineering/*` | 是 |

冲突处理：

1. 用户当前明确指令优先。
2. `AGENTS.md` 的仓库规则优先于工程规范。
3. Unicorn Part I 优先于 MVP Profile。
4. MVP Profile 优先于 implementation plan。
5. 工程规范优先于临时实现偏好。

## 何时读取哪个文件

不要默认读取整个 `docs/engineering/` 目录。只有任务命中下列场景时，才读取对应文件。

| 触发场景 | 读取文件 |
|---|---|
| 架构边界、模块归属、跨模块依赖 | `architecture-guardrails.md` |
| 实施设计、模块接口、迁移分期、store/adapter/evidence 落地 | `implementation-principles.md` |
| Python CLI / engine / schema / subprocess | `python-guidelines.md` |
| Next.js / TypeScript / zod / API route / UI data access | `frontend-guidelines.md` |
| 测试计划、contract tests、flaky 控制 | `testing-guidelines.md` |
| ResultMatrix、Decision、Artifact/Evidence 展示 | `ux-guidelines.md` |
| Work Register、local ticket、GitHub Issue、triage 与完成证据 | `../agents/issue-tracker.md`；`../agents/triage-labels.md` |
| 安全规范索引 / 不确定读哪份安全规范 | `security-guidelines.md` |
| 产品/服务安全：CLI、本地 UI/API、报告、发布包、未来服务化 | `security-service-guidelines.md` |
| 用户 run 安全：secrets、workspace、network caveat、artifact、evidence | `security-user-run-guidelines.md` |
| 开发实施安全：subprocess、env、redaction、workspace、artifact、decision safety | `security-development-guidelines.md` |
| 版本号、CHANGELOG、release evidence、依赖清单、发布提交、tag、dev→main 发布 | `release-process.md` 与开发环境中的 release skill；脚本唯一副本在 `scripts/release/` |

## Implementation Plan Ready Gate

进入 implementation plan 前，相关 spec / profile 必须足够清楚。

一项工作可以进入 implementation plan，当且仅当：

- 所属 Unicorn 模块明确。
- MVP / future 边界明确。
- 输入、输出、持久化位置明确。
- 关键对象的 stable ID 与 schema_version 要求明确。
- 是否影响 Pydantic / zod parity 明确。
- 是否影响 snapshot / replay identity 明确。
- 是否产生 artifact / evidence 明确。
- 错误路径与 caveat 明确。
- 安全与 redaction 边界明确。
- 至少有一条可执行验收测试。
- 不需要用“实现时再决定”补关键语义。

如果不满足 Ready Gate，先补 Unicorn / MVP Profile / test architecture，而不是直接写 implementation plan。

## Documentation Discipline

文档更新遵守单一权威原则。

- 修改长期架构、不变量、模块边界：改 Unicorn Part I。
- 修改 MVP 当前范围、迁移分期：改 MVP Profile。
- 修改测试策略：改 test architecture。
- 修改代码组织、工程原则、技术栈约束、UX 实现约束：改本目录对应文件。
- 修改具体实施任务：改 implementation plan。

不要在 implementation plan 中重新定义 schema，不要在工程规范中复制字段表，不要在 README 中承诺未绑定 Profile 的能力。
