---
title: micro-eval 产品/服务安全规范
doc_type: reference
status: active
created_at: 2026-06-03T09:28+08:00
updated_at: 2026-08-29T09:41+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - engineering
  - security
  - service
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/frontend-guidelines.md
  - docs/releases/
---

# micro-eval 产品/服务安全规范

本文件约束 `micro-eval` 作为产品表面对用户暴露的安全边界，包括 CLI、本地 UI/API、静态报告、发布包，以及未来可能的服务化形态。

## 当前 MVP 服务边界

- MVP 是 local-first 工具，不提供多团队协作、RBAC/SSO、复杂审计或托管服务能力。
- 本地 UI/API 只应读取当前项目允许的 `.micro-eval/` run 数据和 manifest-bound artifact。
- 报告和 UI 不得直接暴露未经过 manifest/ref 边界校验的 raw filesystem path。
- 发布包不得依赖 dev-only 文档或运行时私有资料。

## UI/API 与报告暴露

- API route 必须验证 run/artifact 边界，不能把任意路径作为文件读取入口。
- artifact 内容只通过明确的 `artifact_id` / manifest ref 暴露。
- text/html 报告必须避免注入风险；渲染用户/agent 输出时必须转义或使用安全模板策略。
- UI/Decision 面向用户展示 caveat，而不是隐藏安全降级。

## 发布与分支边界

- `scripts/release/public-projection.toml` 是公开路径分类的唯一 source of truth；所有 tracked 路径必须明确属于 public、private 或 generated，未知/冲突路径必须中止发布。
- `main` 必须与白名单生成的候选公开树完全一致；private、本地产物和历史泄漏路径不得因 merge 继承进入候选树。
- 候选版本必须先完成测试、构建和归档验证，再通过 compare-and-swap 原子更新本地 `main`；失败不得移动 `main`。
- wheel/sdist 必须从候选公开树构建并逐项校验归档清单，不能读取日常 `dev` 工作区中的未跟踪日志、缓存或本地 issue。
- public Git remote 只能接收 verified `main` 和明确批准、指向同一 SHA 的 annotated tag；public remote 出现 `dev` 时发布必须中止，禁止 `--all` 和 `--mirror`。
- 发布 evidence 必须记录安全相关验证结果。
- 发布脚本生成的 `AGENTS.md` / `CLAUDE.md` 只能提供 main 分支必要 guardrails，不应泄露 dev-only 内容。

## 未来服务化边界

如果 `micro-eval` 从本地工具演进为托管服务，必须先补充新的服务安全规范，至少覆盖：

- authentication / authorization；
- tenant isolation；
- audit logging；
- hosted sandbox / network isolation；
- secret storage and rotation；
- data retention and deletion；
- abuse prevention and rate limiting。

## Team Server 服务化安全附录（v0.4）

### 信任模型
- **可信内网假设**：server 部署在团队内网，所有成员互信。
- **无认证**：`X-Micro-Eval-Member` header 为自报身份，仅用于归属记录，不做鉴权。
- 此假设的边界条件：server 不暴露到公网；团队成员不主动伪造身份；浏览器可能访问恶意外部网页。

### CSRF 防护（四层）
1. Content-Type 强制：写接口只接受 `application/json`。
2. 自定义 header 检查：写接口要求 `X-Micro-Eval-Member` header。
3. 无 CORS headers：不返回 `Access-Control-Allow-Origin`。
4. Host header allowlist：拒绝非 allowlist 的 Host header（防 DNS rebinding）。

### config_overrides 白名单
仅允许覆盖：`repetitions`、`timeout_s`、`max_concurrency`。
禁止覆盖：`agent.command`、`workspace`、`output_dir`、`project_root`。

### 归属记录（最小审计）
所有写操作记录 `X-Micro-Eval-Member`。归属记录不可变（workspace.owner 创建后不可更改）。

### 适用范围
本附录仅适用于 `micro-eval serve` 模式。`micro-eval ui` 本地模式不受影响。
