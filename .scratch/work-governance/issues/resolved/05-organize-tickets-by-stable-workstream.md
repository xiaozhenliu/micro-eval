---
id: LOCAL-WORK-GOVERNANCE-05
title: 按稳定 workstream 组织本地 ticket
effort: work-governance
type: governance
status: resolved
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T18:07+08:00
updated_at: 2026-08-29T18:14+08:00
tags:
  - work-governance
  - ticket
related:
  - docs/agents/issue-tracker.md
  - docs/agents/ticket-template.md
  - scripts/check-work-governance.py
  - .scratch/work-governance/map.md
---

# LOCAL-WORK-GOVERNANCE-05 — 按稳定 workstream 组织本地 ticket

## What to build

把 `.scratch/<effort>/` 明确定义为具有稳定范围的 workstream，而不是发布批次、
portfolio lane 或随手收纳新工作的文件夹。每个 workstream 用 `map.md` 声明范围和
边界；`TODOS.md` 的 lane 单独表达何时执行，ticket lifecycle 单独表达执行状态。

迁移被误放进历史 `next-release` workstream 的比较结论 ticket，并把规则落实到
治理文档和 fail-closed 校验器，防止同类漂移再次发生。

## Acceptance criteria

- [x] 治理文档明确区分 workstream、ticket lifecycle 和 portfolio lane，并给出新 ticket 的路由流程。
- [x] 每个包含 ticket 的 workstream 都有 `map.md`，说明 `Scope`、`Boundaries` 和是否继续接收新 ticket。
- [x] 相对时间或兜底名称不能作为新的 active workstream；已存在的 `next-release` 作为 archived 历史 workstream 保留。
- [x] 新 ticket ID 默认由 workstream slug 确定，历史别名只作为显式兼容例外保留。
- [x] work-governance 校验器拒绝缺少 map、向 archived workstream 添加 active ticket、active workstream 使用 vague/relative-time 名称，以及 ID/workstream 前缀不一致。
- [x] `LOCAL-NEXT-12` 在首次提交前迁移为独立的 comparative-decision workstream ticket，`TODOS.md` 和现有文档引用同步更新。
- [x] monid、site-skill、work-governance、comparative-decision 与历史 next-release workstream 都有准确 map。
- [x] 针对性单元测试、仓库治理检查和 `git diff --check` 通过。

## Context

现有存储形状已经接近正确：例如 monid 和 work-governance 各自拥有独立目录，
resolved ticket 也保留在所属 workstream 内。缺口在于 `effort` 只被校验为目录名，
`map.md` 又是可选文件，因此治理无法判断一个新 ticket 是否真正属于该目录。

`next-release` 原本是一组 release-hardening 工作；其 01–11 已全部 resolved。将
Decision Layer 功能继续编号为 `LOCAL-NEXT-12`，混淆了稳定问题域与“下个版本”这一
相对时间概念，也让目录名称在每次发布后失去清晰含义。

## Completion evidence

- 权威规则：`docs/agents/issue-tracker.md` 与 `docs/agents/ticket-template.md`。
- 校验器与测试：`scripts/check-work-governance.py`、`tests/unit/test_work_governance.py`。
- 迁移结果：`LOCAL-COMPARATIVE-DECISION-01` 与各 workstream `map.md`。
- 实现记录：`docs/dev/log/2026-08-29-1814-dev-log-stable-workstream-ticket-governance.md`。
- 验证：治理单元测试 15 passed，work-governance 检查与 `git diff --check` 通过。
