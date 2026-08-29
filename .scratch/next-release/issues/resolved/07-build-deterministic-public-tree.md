---
id: LOCAL-NEXT-07
title: 从白名单构造确定性公开树
effort: next-release
type: task
status: resolved
triage: ready-for-agent
executor: agent
blocked_by:
  - LOCAL-NEXT-06
created_at: 2026-08-29T13:00+08:00
updated_at: 2026-08-29T16:19+08:00
---

# LOCAL-NEXT-07 — 从白名单构造确定性公开树

**What to build:** 发布 Module 从空的候选树恢复 public 路径并生成公开文件，而不是先 merge 全部再删除黑名单；本机 `main` 必须等于候选树。

- [x] 候选树只来自已提交的 source SHA、public 分类和 generated 映射，不读取未跟踪工作区内容。
- [x] `AGENTS.md` 与公开 `.gitignore` 从唯一模板生成，历史上误入 `main` 的文件会在下一次投影自动消失。
- [x] 投影在隔离临时 worktree 中完成，不切换当前 `dev` worktree；失败不污染当前分支。
- [x] 自动化回归验证 public 新文件进入、private 文件排除、旧 main 泄漏清除以及 dev-only 门禁保持有效。

## Context

当前 merge-then-strip 依赖完整黑名单并需要处理 modify/delete conflict。历史提交显示内部计划、安全报告和嵌套 agent 指令曾进入 `main`。

## 给高中实习生的解释

旧做法像先把整个房间装进快递箱，再努力拿出“不该寄”的东西；很容易漏。新做法从空箱子开始，只按白名单放入文件。整个装箱过程发生在临时 worktree（可以理解为临时复印出来的工作台），所以不会切走或弄乱你正在使用的 `dev`。

## Completion evidence

- Implementation trace: `docs/dev/log/2026-08-28-1709-dev-log-fail-closed-public-release.md` and `docs/releases/2026-08-29-v0.4.6-release-evidence.md`.
- Verification: empty candidate-tree construction, generated-file equality, old-main leak removal, and isolated-worktree gates passed.
