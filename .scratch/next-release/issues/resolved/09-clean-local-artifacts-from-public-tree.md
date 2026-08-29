---
id: LOCAL-NEXT-09
title: 清理公开树中的本地产物
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

# LOCAL-NEXT-09 — 清理公开树中的本地产物

**What to build:** 移除已跟踪的本地测试缓存，补齐根目录 ignore，并把当前未分类的本地开发文档放入 private 策略。

- [x] 从 Git 跟踪中移除根目录 `node_modules/.vite/.../results.json`，下一次确定性投影会同时清理 `main`。
- [x] 根 `.gitignore` 覆盖根目录 `node_modules/`、`.omx/`、`.scratch/` 和 `.superpowers/` 等本地产物。
- [x] `CONTEXT.md` 明确归为 private，不再依赖是否有人记得扩充黑名单。
- [x] 策略/CI 能阻止这些路径将来被强制跟踪后进入公开候选树。

## Context

`node_modules/.vite/vitest/.../results.json` 当前同时存在于 `dev` 与 `main`；`CONTEXT.md` 只在 `dev`，但现脚本会在下次发布自动带入 `main`。

## 给高中实习生的解释

测试缓存像做题时的草稿纸：对本机有用，但不属于产品。我们把已经误提交的缓存从 Git 移除，并用 `.gitignore` 告诉 Git 以后别再收它。`CONTEXT.md` 也被明确标成 private，所以它即使在 `dev` 里有提交，也不会进入公开版。

## Completion evidence

- Implementation trace: `docs/dev/log/2026-08-28-1709-dev-log-fail-closed-public-release.md`.
- Verification: tracked local cache removal, root ignore coverage, private classification, and forbidden-public checks passed.
