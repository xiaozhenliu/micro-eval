---
id: LOCAL-NEXT-01
title: 统一执行命令占位符解析
effort: next-release
type: task
status: resolved
triage: ready-for-agent
executor: agent
blocked_by: []
created_at: 2026-08-29T13:00+08:00
updated_at: 2026-08-29T16:19+08:00
---

# LOCAL-NEXT-01 — 统一执行命令占位符解析

**What to build:** 让用户在 agent command、workspace setup command 和 command expectation 中使用 `{python}` 等命令占位符时获得一致、可预测的行为，不再需要针对不同执行入口手工改用 `python3` 等平台相关命令。

- [x] `{python}` 等受支持占位符在 agent command、workspace setup 和 command expectation 三条用户路径中采用同一解析语义。
- [x] 非占位符参数保持原样，且命令执行继续避免 shell 字符串插值。
- [x] 用户文档说明可用占位符及适用范围，并覆盖跨执行入口的回归验证。
- [x] 相关 Python 测试、契约检查和安全检查通过。

## Completion evidence

- Commit: `ee6762a`.
- Verification: shared argv-only placeholder resolution covers all three command entry points; 55 focused tests passed.
- Release trace: `CHANGELOG.md` v0.4.5.
