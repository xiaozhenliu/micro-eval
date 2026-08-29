---
title: LOCAL-NEXT — Release hardening effort map
doc_type: reference
status: active
created_at: 2026-08-29T13:00+08:00
updated_at: 2026-08-29T16:19+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - work-record
  - effort-map
related:
  - docs/agents/issue-tracker.md
---

# LOCAL-NEXT — Release hardening effort map

This map groups the durable release-preparation tickets. It is a navigation
record, not a second Work Register; unfinished work is indexed only by
`TODOS.md`.

## Decisions-so-far

- `LOCAL-NEXT-01` — [统一执行命令占位符解析](issues/resolved/01-unify-command-placeholder-resolution.md)
- `LOCAL-NEXT-02` — [保证 Team Server 超时后的运行状态一致](issues/resolved/02-persist-terminal-run-status-on-worker-timeout.md)
- `LOCAL-NEXT-03` — [准备并完成下一次正式发布](issues/resolved/03-prepare-and-complete-next-formal-release.md)
- `LOCAL-NEXT-04` — [支持仅本地的发布投影](issues/resolved/04-support-local-only-release-projection.md)
- `LOCAL-NEXT-05` — [闭合正常 workspace 生命周期](issues/resolved/05-close-normal-workspace-lifecycle.md)
- `LOCAL-NEXT-06` — [集中公开投影策略并默认拒绝未知路径](issues/resolved/06-centralize-public-projection-policy.md)
- `LOCAL-NEXT-07` — [从白名单构造确定性公开树](issues/resolved/07-build-deterministic-public-tree.md)
- `LOCAL-NEXT-08` — [收紧 wheel 与 sdist 公开产物](issues/resolved/08-harden-release-artifacts.md)
- `LOCAL-NEXT-09` — [清理公开树中的本地产物](issues/resolved/09-clean-local-artifacts-from-public-tree.md)
- `LOCAL-NEXT-10` — [使用验证回执分离投影与远端 push](issues/resolved/10-verified-release-receipt-and-push.md)
- `LOCAL-NEXT-11` — [一键生成并发布 verified 公开版本](issues/resolved/11-one-command-verified-public-release.md)
