# LOCAL-NEXT-11 — 一键生成并发布 verified 公开版本

**What to build:** 把公开版本发布收敛成一个深 Release Module 和一个小命令界面：一个命令在本地构造、测试并验证 public 候选版本；远端发布是第二个显式动作，只能原子推送 verified `main` SHA，以及可选但必须指向同一 SHA 的 annotated tag。

ID: LOCAL-NEXT-11
Type: task
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: LOCAL-NEXT-06, LOCAL-NEXT-07, LOCAL-NEXT-08, LOCAL-NEXT-10

- [x] 默认一键 stage 从 clean `dev` 构造和验证候选版本，全程不访问远端；任何候选测试、UI build 或产物检查失败时，本地 `main` 保持原值。
- [x] Release Module 在全部验证通过后才通过 compare-and-swap 原子更新本地 `main`，回执具有明确的 `staged`/`verified`/`published` 状态并支持安全重试。
- [x] publish 必须要求完整 `--expected-sha` 和 verified 回执，只推送精确 SHA 到公开 remote 的 `main`；公开 remote 如果已经存在 `dev` 分支则 fail closed。
- [x] 可选 tag 必须显式提供、符合 `vX.Y.Z`、与回执版本一致、为 annotated tag，并与 `main` 在一次 atomic push 中指向同一个 verified commit。
- [x] public GitHub CI 不再以公开 `dev` push 为触发条件；Skill、`AGENTS.md` 和 release process 明确 public remote 永远不能接收 private `dev`。
- [x] 真实临时 Git/bare-origin 集成测试覆盖成功 stage、候选验证失败不移动 `main`、安全重试、缺失/过期回执、公开 `dev` 拒绝、精确 main push 和 atomic tag push。

## 给高中实习生的解释

“一键发布”不是把正在写作业的桌面直接直播到网上。第一个按钮像自动质检流水线：从空箱子开始，只装白名单文件，测试两遍，检查安装包，最后得到一件带 SHA 身份证和 verified 质检章的本地成品。第二个按钮才负责上传，而且只认这一个 SHA。只要质检中间失败，商店货架 `main` 不会换货；tag 也必须绑在同一件成品上，不能误绑到含 private 内容的 `dev`。

## Security invariants

- Skill 是操作手册，不是安全门禁；人、Agent 和 CI 必须调用同一 Release Module。
- public/private/generated 分类只来自 `scripts/release/public-projection.toml`。
- 所有 subprocess 使用 argv-only；不得使用 shell interpolation。
- public Git remote 只允许投影后的 `main` 和显式批准的 tag，绝不允许 `dev`、`--all` 或 `--mirror`。
- 不在回执、日志或 release evidence 中记录 secrets、环境变量或本机凭证路径。

## Completion evidence

- Implementation trace: `docs/dev/log/2026-08-29-0941-dev-log-one-command-verified-release.md` and `docs/releases/2026-08-29-v0.4.6-release-evidence.md`.
- Verification: focused release integration coverage exercises stage retry, receipt binding, public-`dev` rejection, exact main publication, and atomic annotated-tag publication.
