# LOCAL-NEXT-06 — 集中公开投影策略并默认拒绝未知路径

**What to build:** 用单一、机器可读的策略把 `dev` tracked 路径分类为 public、private 或 generated；发布入口、验证和文档不再维护彼此漂移的排除列表。

ID: LOCAL-NEXT-06
Type: task
Status: resolved
Triage: ready-for-agent
Executor: agent
Blocked by: None

- [x] 每个 tracked 路径必须且只能命中 public、private 或 generated；未知或冲突分类使发布失败。
- [x] `CONTEXT.md`、内部 docs、agent/tool 本地目录有明确 private 分类，公开代码、测试、站点和 release 工具有明确 public 分类。
- [x] known-sensitive 路径和私钥内容检查作为纵深防御，不能代替 public 白名单。
- [x] 策略检查具有正常、未知路径、冲突路径和敏感 public 路径的自动化验证。

## Context

当前 `DEV_ONLY_PATTERNS` 是开放世界黑名单。新增 tracked 路径默认进入 `main`；`CONTEXT.md` 已成为未分类实例，而且脚本、Skill、AGENTS 和 release process 的列表已经漂移。

## 给高中实习生的解释

黑名单像“除了这几个人，其他人都能进”；漏写一个名字就可能放错人。白名单像活动签到表：文件只有明确写成 public 才能发布，写成 private 就留在本机，generated 表示发布时从指定模板制作。新文件没登记或同时登记两类，发布会停下来请维护者判断。

## Completion evidence

- Implementation trace: `docs/dev/log/2026-08-28-1709-dev-log-fail-closed-public-release.md`.
- Verification: public/private/generated classification, unknown/conflicting path, sensitive-path, and private-key marker checks passed.
