# LOCAL-NEXT-04 — 支持仅本地的发布投影

**What to build:** 让维护者可以通过正式发布入口只把 `dev` 投影到本地 `main` 并完成验证，而不会隐式推送远端；远端 push 必须成为单独、显式授权的动作。

ID: LOCAL-NEXT-04
Type: task
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: None

- [x] 发布入口提供明确的 local-only/no-push 模式，默认行为和帮助文本不会让维护者误判远端副作用。
- [x] 只有显式选择 push 模式时才执行 `git push origin main`，并在执行前显示目标 remote/branch。
- [x] local-only 和 push 两条路径都有自动化回归验证，且现有 dev-only 投影、测试和 main 校验门禁保持不变。
- [x] 发布 Skill、release process 文档和脚本用法保持一致。

## Context

During the v0.4.5 release, the maintainer authorized local projection only, but `scripts/release-to-main.sh dev main` performed an unconditional push to `origin/main`. The release itself passed all gates, but the script lacked a way to honor the requested local-only boundary.

## 给高中实习生的解释

把 `main` 想成准备寄给公众的成品，`origin/main` 想成已经放到网上的成品。以前脚本做好本地成品后会立刻上传，来不及让人检查。现在默认只在本机做好并验证；上传是另一条命令，而且必须明确写出要上传的完整 commit SHA。

## Completion evidence

- Implementation trace: `docs/dev/log/2026-08-28-1642-dev-log-local-only-release-projection.md` and the superseding fail-closed release log.
- Verification: isolated release integration coverage exercises local-only and explicit publication paths; no project remote was changed during implementation.
