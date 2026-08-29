# LOCAL-NEXT-10 — 使用验证回执分离投影与远端 push

**What to build:** local projection 生成绑定 source SHA、main SHA、策略摘要和验证状态的本地回执；远端 push 是单独命令，只能推送回执中已验证的精确 SHA。

ID: LOCAL-NEXT-10
Type: task
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: LOCAL-NEXT-07, LOCAL-NEXT-08

- [x] 默认命令只生成、验证本地 `main` 和回执，不访问远端。
- [x] push 命令要求显式 `--expected-sha`，核对本地 `main`、策略摘要和 verified 回执后才显示并执行 `origin/main` 更新。
- [x] main 验证、产物验证和敏感路径检查全部发生在 push 之前；外部文档步骤不再承担最后安全门禁。
- [x] CI 执行策略与产物验证；自动化覆盖过期 SHA、缺失/未验证回执、local-only 和成功 push。

## Context

当前 `--push` 虽然显式，但投影与 push 仍在同一运行中，而且 Skill 中的部分 main 校验发生在脚本返回以后。

## 给高中实习生的解释

验证回执像质检员盖章的收据，里面绑定了唯一 commit SHA、所用白名单版本和检查结果。上传命令只认“当前、verified、SHA 完全一致”的回执；拿旧 SHA、没有回执或只有未完成回执都不能 push。这样即使有人输错命令，也不会把尚未验收的版本发到网上。

## Completion evidence

- Implementation trace: `docs/dev/log/2026-08-28-1709-dev-log-fail-closed-public-release.md` and `docs/dev/log/2026-08-29-0941-dev-log-one-command-verified-release.md`.
- Verification: missing, stale, and unverified receipts are rejected; exact-SHA local-only and temporary-origin publication paths pass.
