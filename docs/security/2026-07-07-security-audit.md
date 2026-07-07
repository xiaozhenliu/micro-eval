---
title: micro-eval 安全审计报告 — v0.4.2 全量复审
doc_type: audit
status: completed
created_at: 2026-07-07T00:00+08:00
auditor: Claude Opus 4.6 (1M context)
scope: v0.4.2 全量代码库复审（Team Server + Conversational Evaluation + 执行/评测层 + UI/API + secrets 链 + 发布边界）
tags:
  - security
  - audit
related:
  - docs/engineering/security-guidelines.md
  - docs/engineering/security-development-guidelines.md
  - docs/engineering/security-user-run-guidelines.md
  - docs/engineering/security-service-guidelines.md
  - docs/security/2026-06-20-security-audit.md
  - docs/security/2026-06-15-security-audit.md
---

# micro-eval 安全审计报告 (2026-07-07)

## 审计方法

四路并行审计（Python 执行/评测层、Team Server 层、UI/API 层、secrets 链 + 发布边界），逐条对照三层安全规范（`security-development-guidelines.md` / `security-user-run-guidelines.md` / `security-service-guidelines.md`）。所有 HIGH/MEDIUM 发现与全部历史 finding 状态均由主审计（Opus 4.6）在代码中二次核验到 `file:line`，非机械照搬子审计结论。

审计覆盖版本：v0.4.2（含 2026-06-20 上次审计后的 team-server member journey 修复批次 A1–A6/B7–B10/C11–C15）。

## 总体结论

核心执行层防线依旧扎实：subprocess 全程 argv-only（零 `shell=True`）、host env allowlist、secrets 声明式注入、workspace 路径双重收敛、artifact 的 symlink/hardlink/oversized 防护完整。**XSS 面干净**（全库零 `dangerouslySetInnerHTML`，agent 输出全部走 JSX 文本转义）。

但本次复审暴露 **1 个 HIGH（新发现的真实路径穿越链）**，且上次审计标记为 P1 的两项（F1 Host allowlist、F2 bridge 泄漏）**至今零进展**。当前 Team Server 对信任模型中明确列出的"浏览器访问恶意外部网页"威胁，实际只剩"自定义 header"一层在防守，而该层可被 DNS rebinding 击穿。

| 严重度 | 数量 | 编号 |
|--------|------|------|
| HIGH | 1 | H1 |
| MEDIUM | 7 | M1–M7 |
| LOW | 10 | L1–L10 |
| INFO | 5 | I1–I5 |

---

## 合规项（通过）

| # | 规范条目 | 状态 | 实现位置 |
|---|---------|------|---------|
| 1 | 禁止 shell interpolation，subprocess argv-only | **PASS** | `engine/adapter.py:83` `create_subprocess_exec(*argv)`；`engine/agent_bridge.py:39`；`cli/serve.py` `Popen([...])`；全 `src/` 零 `shell=True`/`os.system`；UI 全部 `execFileSync(bin,[...])` |
| 2 | host env allowlist + 仅声明 secrets 注入 | **PASS** | `adapter.py:238`（`inherited_env_keys`）+ `adapter.py:246-250`（仅 `required_secrets`，缺失 `AdapterError`）；`MICRO_EVAL_SECRET_` 前缀强制 `configuration.py:61-67` |
| 3 | 持久化/返回 UI 文本先 redact | **PASS（2 处 LOW 缺口 L3/L4/L6）** | stdout/stderr `adapter.py:116-117`；judge rationale `llm_judge.py:117`；会话 assistant 每轮 `conversational_judge.py:74`；bridge stderr `kernel.py:363` |
| 4 | agent cwd 收敛在 workspace，不越界写 | **PASS** | 单轮 `kernel.py:166`、会话 `kernel.py:352` cwd=prepared.path；源路径越界拒绝 `git_worktree.py:154-164` |
| 5 | artifact 仅 manifest-bound 暴露 | **PASS** | `artifacts/route.ts:44-59` 先查 `run.artifacts.find` 再 resolve+realpath 双检；本地 `lib/api.ts:93-115` 同构 |
| 6 | artifact symlink/hardlink/oversized 防护 | **PASS** | `adapter.py:285-321`（symlink 删除、`st_nlink>1` 硬链接拒绝、resolve 越界拒绝）；`artifact_store.py:40-72` |
| 7 | workspace 路径穿越防护（resolve_path） | **PASS** | `workspace.py:25-41` regex + resolve + strict resolve 双重前缀；TS 镜像 `workspace-api.ts:5-21` |
| 8 | config_overrides 白名单 | **PASS（功能缺口 L10）** | `build_plan.py:39-43` `{repetitions, timeout_s, max_concurrency}`，越界 exit(1)；`agent.command`/`workspace`/`output_dir`/`project_root` 无注入路径 |
| 9 | CSRF 层2 自定义 header | **PASS** | 所有 server-mode 写接口调用 `validateWriteRequest`（`server-validation.ts:21-27`） |
| 10 | CSRF 层3 无 CORS header | **PASS** | 全 `ui/src` 零 `Access-Control-*`；`next.config.ts` 无 headers 配置 |
| 11 | member name 校验/无 CRLF/无 HTML 注入 | **PASS** | `MEMBER_RE ^[a-zA-Z0-9._-]{1,64}$`（`server-validation.ts:5`）；渲染走 JSX 文本节点 |
| 12 | workspace.owner 创建后不可变 | **PASS** | `workspace.py:142` `allowed={"name","description","status"}`；CLI/UI PATCH 均无 owner 字段 |
| 13 | cellId 校验（2026-06-15 F1） | **已修复** | 全部消费点先 `decodeURIComponent` 再与 `run.json` 的 `cell_id` 做成员资格比对，不存在则 404；从不参与路径拼接 |
| 14 | 发布脚本本体（无注入/无 --force） | **PASS** | `release-to-main.sh` 变量全引号、无用户输入进 shell、仅 `git push origin main`；`preflight-release.sh` 主动 grep 禁用 `shell=True` |
| 15 | 依赖/CI 结构 | **PASS** | 无 postinstall/git+http 依赖；CI 触发器为 `pull_request`（非 `pull_request_target`），`permissions: contents: read`，无 secrets echo |

---

## 发现项

### H1 [HIGH] — template_id 路径穿越：POST /api/workspaces 可把任意 server 可读目录复制进 workspace（新发现）

**位置**: `ui/src/app/api/workspaces/route.ts:11,47` + `src/micro_eval/server/workspace.py:58,70-81`

**链路**:
```ts
// route.ts:11 — 无字符集限制
const CreateWorkspaceSchema = z.object({
  template_id: z.string().min(1).max(64).nullable().default(null),
});
// route.ts:47 — 原样透传
if (input.template_id) args.push("--template", input.template_id);
```
```python
# workspace.py:58 — 仅 exists() 检查，无 regex、无 resolve 前缀校验
tpl_dir = self.data_root / "templates" / template_id
if not tpl_dir.exists():
    raise WorkspaceError(...)
for item in tpl_dir.iterdir():   # 复制目录内容进新 workspace
    ...
```

**机理**: pathlib 语义下，`Path(".../templates") / "/etc"` 会被绝对路径**整体替换**为 `/etc`；`template_id="../../../etc/ssh"`（≤64 字符）同样上跳穿越。传入后 `tpl_dir.exists()` 通过，`iterdir()` 遍历目标目录，非 symlink 的文件被 `shutil.copy2` 复制进成员 workspace。成员随后用自控的 `eval.yaml` + agent 读出内容即可外传——形成**完整的任意文件读取链**，且读取以 server 进程用户身份进行（跨越了成员本地 OS 权限边界）。

**规范引用**: `security-service-guidelines.md:32`（"API route 不能把任意路径作为文件读取入口"）；`security-development-guidelines.md`（路径穿越必须被拒绝）。上次审计合规表 #12 声称"template ID 全部有 regex 限制"——该声明对 `workspaces` POST 路径**不成立**（`safeTemplateId` 存在于 `server-validation.ts:82` 但此 route 未调用）。

**缓解因素**: 可信内网信任模型下成员已被信任；但（a）跨越了 server 进程用户 vs 成员 OS 用户的权限边界；（b）叠加 M1（无 Host allowlist）后，DNS rebinding 可让外部恶意网页触发此写接口。

**修复**:
1. `workspaces/route.ts` 对 `template_id` 套用收紧后的正则（`safeTemplateId` 需改为排除纯点名：`/^(?!\.+$)[a-zA-Z0-9._-]{1,64}$/`）。
2. Python 侧 `WorkspaceManager.create` 与 `TemplateRegistry.get/update/delete`（`template.py:110-158`，CLI 面同样未校验）统一加 template_id regex + resolve 前缀检查，复用 `resolve_path` 的同构逻辑。

---

### M1 [MEDIUM] — Host header allowlist 完全缺失（DNS rebinding）— 承接 2026-06-20 F1，未修复

**位置**: `ui/src/middleware.ts`（**不存在**，`find ui/src -name middleware.*` 零结果）；`server/models.py:60` `allowed_hosts` 为死字段（全库零消费者）；`cli/serve.py` 默认绑定 `0.0.0.0`。

**问题**: CSRF 四层防护中唯一防 DNS rebinding 的第 4 层从未实现。rebinding 成功后攻击页面与 server 同源，可自由携带 `X-Micro-Eval-Member`，层 1/2 全部失效。设计文档 §14.6 的验收用例 `test_host_header_allowlist_rejects_unknown` / `test_host_header_dns_rebinding` 亦无对应实现。

**修复**: 新增 `ui/src/middleware.ts`，`serve.py` 把 `server.json` 的 `allowed_hosts` 经 env 注入，middleware 校验 `Host` header，不匹配返回 400，默认含 `localhost:{port}` / `127.0.0.1:{port}`。此改动可与 M2、M3 合并在同一 middleware 中解决。

---

### M2 [MEDIUM] — Content-Type 缺失时写请求被放行 — 承接 2026-06-20 F3，未修复

**位置**: `ui/src/lib/server-validation.ts:14-15`
```ts
const contentType = request.headers.get("content-type");
if (contentType && !contentType.includes("application/json")) { ... }  // header 缺失 → 放行
```
**问题**: `fetch(url,{method:"POST",body:new Blob([json],{type:""})})` 可发出无 Content-Type 的跨域 simple request 绕过本层。规范要求"强制"，当前为"可选"。

**修复**: `if (!contentType || !contentType.includes("application/json")) return 400;`。并补 `server-validation.ts` 的否定测试（当前 `ui/src/lib/__tests__/` 无此文件测试）。

---

### M3 [MEDIUM] — 本地模式写接口在 serve 模式下仍暴露，绕过全部 CSRF 层与归属记录

**位置**: `ui/src/app/api/runs/[id]/cells/[cellId]/evaluate/route.ts:18-43`（POST 无 `isServerMode()` gate、无 `validateWriteRequest`）。

**机理**: `serve.py` 用 `next start` 跑同一 app，本地 route 树与 server route 树同时可达。任意来源页面可 `POST /api/runs/{id}/cells/{cellId}/evaluate`，无自定义 header、无 Content-Type 约束（`request.json()` 不校验 Content-Type），触发 `execFileSync(uv, ["run","micro-eval","apply-evaluation",...])` 篡改宿主项目评测结论，且**无 member 归属**。

**规范引用**: `security-service-guidelines.md` 附录"所有写操作记录 X-Micro-Eval-Member" + "本地 UI/API 只应读取当前项目允许的数据"。

**修复**: serve 模式下本地 route 树（evaluate/runs/trends 等）统一 404，或在 M1 的 middleware 中按路径前缀拦截。

---

### M4 [MEDIUM] — bridge subprocess 泄漏窗口 — 承接 2026-06-20 F2，未修复

**位置**: `src/micro_eval/evaluation/conversational_judge.py:60-84`

`await bridge.start()`（第 60 行）到 `try:`（第 84 行）之间的 23 行（`conversation_log`、`model_callback` 定义、`ConversationalGolden(...)` 构造 78-82）不在 try/finally 保护内。若 `ConversationalGolden` 构造抛异常（如 deepeval 升级后字段校验变化），`bridge.stop()`（第 101 行）不执行，agent 子进程泄漏。

**规范引用**: `security-user-run-guidelines.md:47`（stop() 必须由 finally 保证）。

**修复**: 把 `bridge.start()` 之后全部代码移入同一 try，或改用 async context manager（`__aenter__`/`__aexit__`）。约 10 分钟。

---

### M5 [MEDIUM] — BridgeError 被吞，agent 死亡后会话继续模拟并被评分

**位置**: `conversational_judge.py:70-76` + `:114`
```python
except BridgeError as exc:
    response = f"[bridge error: {exc}]"      # 占位文本，模拟继续跑满 max_turns
...
status=CellStatus.passed if exit_code is None or exit_code == 0 else CellStatus.error  # :114
```
**问题**: agent 中途死亡时 bridge 正确抛 `BridgeError`，但 callback 转成占位文本继续，产生的"对话"随后正常进入 `score_conversation` 评分；若 agent 崩溃后以 exit 0 退出，该 cell 仍判 `passed`。这违反"证据不可信时不得产生强结论"。

**规范引用**: `security-user-run-guidelines.md:46` + Decision Safety。

**修复**: callback 捕获 BridgeError 后置中止标志；凡出现 bridge error 的会话将 cell 判为 `error`/加 caveat，不送评分。

---

### M6 [MEDIUM] — worker.pid 接管不验证进程身份，且 check→write 存在竞态

**位置**: `src/micro_eval/server/worker.py:38-47`
```python
os.kill(old_pid, 0)          # 只验 PID 存在，不验身份（PID 复用误判）
...
except OSError:
    pass                     # EPERM（进程属他人）→ 落穿到覆盖写
pid_path.write_text(str(os.getpid()))   # 与上面 check 之间无 O_EXCL/flock
```
**问题**: (a) PID 复用时误判"已有 worker 在跑"并 `sys.exit(1)`；(b) EPERM 分支静默落穿，覆盖活 worker 的 PID 文件；(c) 无原子性，两个 worker 可同时通过检查并发运行——破坏 v0.4 "串行队列"核心不变量（SQLite `dequeue_next` 能防同一 job 双跑，但防不住两个不同 job 并发）。

**修复**: `os.open(pid_path, O_CREAT|O_EXCL|O_WRONLY)` 原子创建；EPERM 视为"占用"而非 pass；PID 文件写入启动时间戳或校验 cmdline 含 `micro_eval` 以验身份。

---

### M7 [MEDIUM] — 内部安全审计报告存在泄漏到公开 main 分支的通道

**位置**: `scripts/release-to-main.sh:20` `DEV_ONLY_PATTERNS`（**不含 `docs/security`**）；`git ls-tree -r main` 显示 main **已经跟踪** `docs/superpowers/plans/2026-06-15-documentation-restructure-plan.md` 与 `ui/CLAUDE.md`。

**问题**: `docs/security/` 在 dev 上被跟踪（含本报告与历史报告，均带未修漏洞的 `file:line` 细节），但 release 脚本的 strip/verify 循环只遍历 `DEV_ONLY_PATTERNS`，拦不住它。main 的 `.gitignore` 虽有 `docs/security/`，但 **gitignore 不阻止 merge 带入已跟踪文件**（CLAUDE.md 中"main 的 .gitignore 会自动排除"的说法不准确）。证据表明该机制已经失效一次：main 上已存在一个本应排除的 `docs/superpowers` 文件。

**风险**: 若 main 为公开仓库，等于对外披露未修复漏洞的精确位置。

**修复**:
1. `DEV_ONLY_PATTERNS` 与 `MAIN_GITIGNORE_EXTRAS` 补入 `docs/security`、`.understand-anything`。
2. 在 main 上 `git rm --cached docs/superpowers/plans/2026-06-15-documentation-restructure-plan.md ui/CLAUDE.md` 并提交（勿等下次发布）。
3. release pattern `"CLAUDE.md"` 改为 `"*CLAUDE.md"` 以覆盖 `ui/CLAUDE.md`。

---

### LOW / INFO 发现

| 编号 | 级别 | 标题 | 位置 | 要点 |
|------|------|------|------|------|
| L1 | LOW~MED | config PUT/GET 跟随 `eval.yaml` symlink | `workspaces/[id]/config/route.ts:59-66` | `resolveWorkspacePath` 只 realpath 目录，未查 eval.yaml 本身；agent 在 Level 0 无沙箱下可在 workspace 内植入 symlink，成员一次"保存配置"即以 server 用户身份写任意路径。修复：写前 `lstatSync` 拒绝非 regular file，或临时文件 + rename |
| L2 | LOW | runId/templateId 正则放过 `..` | `RUN_ID_RE=/^[A-Za-z0-9_.:-]+$/` 等 | `runId=".."` 可上跳一级（仍在 `.micro-eval` 内，`RunSchema.parse` 兜底）；template 侧被 artifact 路由 resolve 双检挡下。修复：正则排除纯点名或补 resolve 前缀检查 |
| L3 | LOW | kernel 错误路径 stderr 未 redact | `engine/kernel.py:170-176` | except 分支 `stderr=str(exc)` 时 redactor 仍为空 `Redactor({})`，写入 stderr.txt；与 `_isolated_failure_result`（`kernel.py:120` 用 `Redactor.from_env()`）不一致。异常文本为路径/git stderr，泄漏概率低 |
| L4 | LOW | worker 异常原文写入 queue.db | `server/worker.py` `except` 分支 | `db.update_status(..., error=str(exc))` 未过 Redactor。同 L3 处理 |
| L5 | LOW | SubprocessBridge stderr 无上限、会话期不排空 | `engine/agent_bridge.py:86-88` | `stderr.read()` 无 cap（对比单轮 `_read_limited`）；会话期 pipe 不消费，agent 大量写 stderr 会写满 OS buffer 阻塞→turn 超时。修复：按 `output_cap_bytes` 截断 + 后台限量排空 |
| L6 | LOW | conversation.json 用户轮次未 redact | `conversational_judge.py:66` | user 轮由 simulator LLM 生成、按构造不含宿主 secrets，风险低；严格对照规则属缺口。修复：落盘前对全量 log 统一 redact 一次 |
| L7 | LOW | 模板复制 hardlink 未覆盖 + 顶层 symlink 排除静默 | `workspace.py:75-76`；`template.py` | 嵌套 symlink 已由 `_template_ignore` 排除并 warning（F4 主修复）；但 hardlink（`st_nlink>1`）无检测，`workspace.py:75` 顶层 symlink `continue` 无日志。修复：补 `logger.warning` + hardlink 检测 |
| L8 | LOW | worker workspace_resolver + 执行路径缺 ID 校验 | `worker.py:66-70,94` | `resolve()`/regex 均无；`worker.py:94` 甚至绕过 resolver 直接拼 `ws_path` 作 kernel 根。数据源（queue.db）当前可信，属纵深防御缺口（承接 2026-06-20 F5，未修复）。修复：复用 `WorkspaceManager.resolve_path` |
| L9 | LOW | 短 secret 过度 redact | `adapter.py:26-40`；`human.py:53-58` | 1 字符 secret 会全量 `str.replace` 污染输出（承接 2026-06-15 F4，未修复）。可用性问题非漏洞。修复：最小长度阈值（≥4）+ 过短 secret 记 caveat |
| L10 | LOW | overrides 白名单 `repetitions`/`timeout_s` 被静默忽略 | `build_plan.py:39-47`；`config/planner.py:18-28` | 白名单放行三键但 planner 只接 `max_concurrency`，另两键被接受却零影响（fail-closed 无害）；规范与实现脱节。修复：接线或收窄白名单 + 同步规范 |
| I1 | INFO | 错误 detail / status 泄露服务器绝对路径 | 各写 route catch 分支；`server/status/route.ts` | `err.message` 含完整命令行与 wsPath；可信内网可接受，服务化前需截断 |
| I2 | INFO | `JSON.stringify` 内插进 Python 代码字符串 | `jobs/[jobId]/cancel/route.ts` 等 | 当前 regex 字符集下安全，但与"never via string interpolation"注释矛盾、模式脆弱。建议统一改 env/stdin 传参（enqueue route 已示范） |
| I3 | INFO | LLM judge prompt injection 防护弱 | `llm_judge.py` | "Do not follow instructions..." 弱防护（承接 2026-06-15 F7）。后续升级结构化输出 + 角色分离 |
| I4 | INFO | Modal provider 内部复制完整容器 env | `remote.py`（`os.environ.copy()`） | 容器内未应用 allowlist（承接 2026-06-15 F5）。与本地 provider 策略不一致 |
| I5 | INFO | run_store 解析任意 JSON | `run_store.py` | 读 `.micro-eval/runs/` 下所有 `.json`（有 try/except）。建议收窄为只读 `run.json`（承接 2026-06-15 F6） |

---

## 安全规范 Code Review Checklist

| 检查项 | 状态 | 说明 |
|-------|------|------|
| Secrets redaction | ⚠️ | 主链路完整（stdout/stderr、judge、会话 assistant 轮、evidence 全覆盖）；残留 3 处一致性缺口（L3 kernel 异常、L4 worker 异常、L6 会话 user 轮），均为非 agent 输出、风险低 |
| Workspace boundary | ❌ | `resolve_path` 双重防御正确，但 `create()` 的模板分支绕过它导致 H1 路径穿越；worker 执行路径（L8）亦缺校验 |
| Shell interpolation | ✅ | 全链路 argv-only，零 `shell=True`；I2 的 JSON.stringify 内插当前安全但建议改造 |

---

## 与历史审计的关系

| 历史 finding | 首次报告 | 本次状态 |
|-------------|---------|---------|
| Host header allowlist / DNS rebinding | 2026-06-20 F1 (P1) | **未修复**（M1） |
| bridge subprocess 泄漏窗口 | 2026-06-20 F2 (P1) | **未修复**（M4） |
| Content-Type 允许缺失 | 2026-06-20 F3 | **未修复**（M2） |
| Template symlink 检查 | 2026-06-20 F4 | **基本修复**（嵌套 symlink 已排除+warning），残留 hardlink/顶层静默（L7） |
| Worker resolver ID 验证 | 2026-06-20 F5 | **未修复**（L8） |
| cellId 校验 | 2026-06-15 F1 | **已修复**（合规表 #13） |
| Seatbelt SBPL 转义 | 2026-06-15 F2 | 依赖 `safe_path_segment` 上游过滤，未见回归（本次未重点复审） |
| evaluate 错误信息泄露 | 2026-06-15 F3 | **未修复**（I1） |
| 短 secret 过度 redact | 2026-06-15 F4 | **未修复**（L9） |
| Modal 复制完整 env | 2026-06-15 F5 | **未修复**（I4） |
| run_store 解析任意 JSON | 2026-06-15 F6 | **未修复**（I5） |

---

## 建议修复顺序

| 优先级 | 编号 | 问题 | 工作量 |
|--------|------|------|--------|
| **P0** | H1 | template_id 路径穿越（真实任意文件读取链） | 半天（前后端各加 regex + resolve 校验） |
| **P0** | M7 | 内部审计报告泄漏 main 的发布通道 | 1 小时（补 pattern + `git rm --cached`），**下次 release 前必须处理** |
| **P1** | M1 | Host header allowlist（DNS rebinding） | 半天（一个 middleware） |
| **P1** | M3 | serve 模式关闭本地写路由 | 与 M1 合并 |
| **P1** | M2 | Content-Type 强制 | 5 分钟 |
| **P1** | M4 | bridge 泄漏窗口 | 10 分钟 |
| **P2** | M5 | BridgeError 后不再评分 | 半天 |
| **P2** | M6 | worker.pid 原子化 + 身份校验 | 半天 |
| **P3** | L1–L10 | 一致性与纵深防御收尾 | 视情况 |

M1 + M2 + M3 可在同一个 `ui/src/middleware.ts` 改动中一并解决。
