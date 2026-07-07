---
title: micro-eval 安全审计报告 — v0.4.0 Team Server + v0.4.1 Conversational Evaluation
doc_type: audit
status: completed
created_at: 2026-06-20T00:00+08:00
auditor: Claude Opus 4.6 (1M context)
scope: v0.4.0 Team Server + v0.4.1 Conversational Evaluation incremental changes
tags:
  - security
  - audit
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/security-development-guidelines.md
  - docs/engineering/security-user-run-guidelines.md
  - docs/engineering/security-service-guidelines.md
  - docs/security/2026-06-15-security-audit.md
---

# micro-eval 安全审计报告 (2026-06-20)

## 审计范围

增量审计：覆盖 v0.4.0 Team Server 和 v0.4.1 Conversational Evaluation 两个功能的全部代码变更（123 files, ~14,800 行新增），对照三层安全规范逐条检查。

审计覆盖的新增/变更模块：

- **Team Server — Python**: `server/workspace.py`, `server/queue.py`, `server/worker.py`, `server/template.py`, `server/models.py`, `cli/serve.py`, `cli/workspace_cmd.py`, `cli/queue_cmd.py`, `cli/template_cmd.py`, `cli/build_plan.py`
- **Team Server — UI API**: 18 个新增 API route（workspaces CRUD, queue, templates, jobs, config, runs, artifacts, trends, server status）
- **Team Server — UI 库**: `lib/server-validation.ts`, `lib/server-mode.ts`, `lib/workspace-api.ts`
- **Conversational Evaluation**: `engine/agent_bridge.py`, `evaluation/conversational_judge.py`, `engine/kernel.py` (conversational 分支)
- **模型扩展**: `models/task.py`, `models/configuration.py`, `models/run.py`
- **安全测试**: `tests/unit/server/test_security_negative.py`

## 合规项（通过 12 项）

| # | 规范条目 | 状态 | 实现位置 |
|---|---------|------|---------|
| 1 | 禁止 shell interpolation | **PASS** | `agent_bridge.py:42` `create_subprocess_exec(*command)`; `serve.py:44,72` `Popen([...])` argv-only; UI 全部使用 `execFileSync(bin, [...])` |
| 2 | Subprocess argv-only | **PASS** | 全量搜索零 `shell=True`；`queryQueue` 通过 `JSON.stringify` 编码值、上游有 regex 校验 |
| 3 | Env allowlist (agent) | **PASS** | `conversational_judge.py:58-59` 通过 `adapter.build_env()` 构建 allowlist env |
| 4 | Conversation log redaction | **PASS** | `conversational_judge.py:74` 每轮 `redactor.redact(response)` 后才存入 log |
| 5 | stderr redaction | **PASS** | `kernel.py:340` `redactor.redact(adapter_result.stderr)` |
| 6 | Evidence summary redaction | **PASS** | `kernel.py:413-416` + `conversational_judge.py:192` 全部经 redactor 且截断 500 字符 |
| 7 | Workspace 路径穿越防护 (Python) | **PASS** | `workspace.py:25-41` regex + `resolve()` 双重前缀检查 + symlink 解析后再验证 |
| 8 | Workspace 路径穿越防护 (TS) | **PASS** | `workspace-api.ts:7-21` 镜像实现：regex + `path.resolve` + `realpathSync` 双重检查 |
| 9 | Artifact 路径双重检查 | **PASS** | `artifacts/route.ts:47-59` `path.resolve` + `realpathSync` 双重前缀验证 |
| 10 | config_overrides 白名单 | **PASS** | `build_plan.py:39-43` `ALLOWED_OVERRIDES = {"repetitions", "timeout_s", "max_concurrency"}`，超范围直接 exit(1) |
| 11 | 写接口 CSRF 防护 | **PASS** | `server-validation.ts:11-29` Content-Type 检查 + `X-Micro-Eval-Member` 自定义 header |
| 12 | ID 格式校验 | **PASS** | workspace ID `WS_ID_RE`, job ID `safeJobId`, template ID `safeTemplateId`, run ID `RUN_ID_RE`, member name `MEMBER_RE` 全部有 regex 限制 |

## 发现项

### F1 [MEDIUM] — Host Header Allowlist 未实施（DNS Rebinding 风险）

**位置**: `server/models.py:60` 定义了 `allowed_hosts: list[str]` 字段，但全部 UI API route 和 Next.js 层均未使用。

**规范引用**: `security-service-guidelines.md:66` — "Host header allowlist：拒绝非 allowlist 的 Host header（防 DNS rebinding）"

**问题**: 不存在 Next.js middleware。Server 默认绑定 `0.0.0.0:3000`，在可信内网环境中，恶意外部网页可通过 DNS rebinding 技术让域名先解析到 attacker IP、再 rebind 到 `127.0.0.1`，绕过"无 CORS headers"防御，利用浏览器向内网 server 发起写请求。自定义 header `X-Micro-Eval-Member` 能挡住简单 form POST，但 `fetch()` API 可以在 DNS rebinding 场景下发送任意 header。

**风险等级**: MEDIUM — 可信内网假设降低了实际攻击概率，但 spec 明确要求此防护。

**修复建议**: 添加 `ui/src/middleware.ts`，在 server mode 下验证 `Host` header 是否在配置的 `allowed_hosts` 白名单中。默认值至少包含 `localhost:{port}` 和 `127.0.0.1:{port}`。

---

### F2 [MEDIUM] — `simulate_conversation` bridge subprocess 泄漏窗口

**位置**: `conversational_judge.py:57-83`

```python
bridge = SubprocessBridge(...)
await bridge.start()           # subprocess 已启动

conversation_log = []          # ← 如果以下代码抛异常...
main_loop = asyncio.get_running_loop()

def model_callback(...): ...

golden = ConversationalGolden(  # ← ...bridge.stop() 不会被调用
    scenario=task.scenario,
    ...
)

try:                            # try/finally 覆盖不到上面
    ...
finally:
    exit_code, stderr = await bridge.stop()
```

**规范引用**: `security-user-run-guidelines.md:47` — "Zombie process risk: if stop() is not called (e.g., due to unhandled exception in the caller), the subprocess may linger. The execution kernel must ensure stop() is called in a finally block."

**问题**: `bridge.start()` 和 `try/finally` 之间存在多行代码（变量赋值、`model_callback` 定义、`ConversationalGolden` 构造）。如果任何一行抛异常，subprocess 不会被清理。

**风险等级**: MEDIUM — `ConversationalGolden` 构造不太可能抛异常，但违反了防御性编程原则和规范要求。

**修复建议**: 将 `bridge.start()` 之后的所有代码包入同一个 `try/finally` 块：

```python
await bridge.start()
try:
    conversation_log = []
    main_loop = asyncio.get_running_loop()
    # ... rest of the code ...
    test_cases = await asyncio.get_running_loop().run_in_executor(None, _run_simulate)
finally:
    exit_code, stderr = await bridge.stop()
```

---

### F3 [LOW] — Content-Type 检查允许缺失

**位置**: `server-validation.ts:14-19`

```typescript
const contentType = request.headers.get("content-type");
if (contentType && !contentType.includes("application/json")) {
```

**规范引用**: `security-service-guidelines.md:63` — "Content-Type 强制：写接口只接受 `application/json`"

**问题**: 如果请求不带 `Content-Type` header（`contentType === null`），检查被跳过。规范要求"强制"，当前实现为"可选"。

**风险等级**: LOW — `X-Micro-Eval-Member` 自定义 header 是更强的 CSRF 防御层，且后续 `request.json()` 会拒绝非 JSON body。实际攻击面极小，但偏离规范文档。

**修复建议**: 改为 `if (!contentType || !contentType.includes("application/json"))`。

---

### F4 [LOW] — Template 文件复制未检查 symlink

**位置**: `template.py:35-40`, `workspace.py:66-73`

```python
for item in source_dir.iterdir():
    if item.is_dir():
        shutil.copytree(item, dest)
    else:
        shutil.copy2(item, dest)
```

**问题**: `shutil.copytree` 和 `shutil.copy2` 默认跟随 symlink 读取目标文件内容。如果模板源目录中包含指向敏感文件（如 `~/.ssh/id_rsa`）的 symlink，其内容会被复制到 workspace 并暴露给成员。

**风险等级**: LOW — 模板由 admin 通过 CLI 创建（`template create --source`），非任意用户可控。但缺乏纵深防御。

**修复建议**: 复制前检查源目录中是否存在 symlink：

```python
for item in source_dir.rglob("*"):
    if item.is_symlink():
        raise TemplateError(f"symlink not allowed in template source: {item}")
```

---

### F5 [LOW] — Worker `workspace_resolver` 缺少 ID 格式验证

**位置**: `worker.py:57-61`

```python
def workspace_resolver(ws_id: str) -> Path | None:
    ws_path = data_root / "workspaces" / ws_id
    if ws_path.exists():
        return ws_path
    return None
```

**问题**: 未验证 `ws_id` 格式（无 regex、无 symlink 解析检查）。虽然值来自 SQLite 队列（可信来源），但 `WorkspaceManager.resolve_path` 有完整验证逻辑，此处应复用以保持一致性和纵深防御。

**风险等级**: LOW — 数据源可信，但不符合 defense-in-depth 原则。

**修复建议**: 复用 `WorkspaceManager.resolve_path` 或至少加上 `_WS_ID_RE` 正则检查。

---

## 安全规范 Code Review Checklist

| 检查项 | 状态 | 说明 |
|-------|------|------|
| Secrets redaction | ✅ | 全链路覆盖：agent 回复（每轮 redact）、stderr、evidence summary、评分 rationale 均经 `Redactor.redact()` 处理后才持久化或返回 UI |
| Workspace boundary | ✅ | 双重防御：regex ID 格式验证 + `resolve()`/`realpathSync` 前缀检查，Python 和 TS 两侧同构实现；artifact 访问同样经过前缀验证 |
| Shell interpolation | ✅ | 全部使用 argv-only 形式（`create_subprocess_exec`、`Popen([...])`、`execFileSync` list args）；零 `shell=True`；`queryQueue` 值嵌入通过 `JSON.stringify` 且上游有 regex 校验 |

## 与上次审计 (2026-06-15) 的关系

上次审计覆盖了 v0.3.x 全量代码库。本次为增量审计，仅覆盖 v0.4.0/v0.4.1 新增变更。上次发现的 F1（cellId 校验）和 F4（短 secret 过度 redact）状态未变，仍建议修复。

## 总结

**总体评估**: 增量变更安全态势**良好**。

- 0 个 shell injection 漏洞
- 0 个 path traversal 漏洞
- 0 个 XSS 漏洞
- 2 个 MEDIUM 发现（F1 Host header 未实施、F2 bridge 泄漏窗口）
- 3 个 LOW 发现（F3 Content-Type、F4 symlink、F5 resolver）

**建议优先修复**:

| 优先级 | 编号 | 问题 | 工作量 |
|--------|------|------|--------|
| **P1** | F1 | Host header allowlist 未实施 | 半天（一个 middleware 文件） |
| **P1** | F2 | bridge subprocess 泄漏窗口 | 10 分钟（扩大 try/finally 范围） |
| **P2** | F3 | Content-Type 允许缺失 | 5 分钟 |
| **P3** | F4 | Template symlink 检查 | 30 分钟 |
| **P3** | F5 | Worker resolver ID 验证 | 10 分钟 |
