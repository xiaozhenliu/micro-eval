# Team Server 成员旅程修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 本项目禁止 TDD：每个任务按"实现 → 验证"执行，测试作为验收与回归手段在实现后补充。

**Goal:** 修复 `docs/bug_reports/2026-07-02-1630-team-server-member-journey-findings.md` 的 15 个问题，使新成员能在 10 分钟内不借助 CLI 与他人，在浏览器中完成完整评测旅程。

**Architecture:** 三批推进——第一批接通旅程（前端接线 + 页面渲染模式），第二批加固服务进程与模板/workspace 生命周期，第三批补引导与说明。后端 API 已验证可用，绝大部分改动在 `ui/src/` 与 `src/micro_eval/cli/serve.py`、`src/micro_eval/server/` 两处。

**Tech Stack:** Next.js（App Router，服务端组件 + 少量 client 组件）、TypeScript、Typer/Python 3.11。

## Global Constraints

- 禁止 TDD；先实现后验证。测试新增仅作验收/回归。
- 动手前读 `docs/engineering/security-guidelines.md`；批次 2 涉及 subprocess/PID/文件复制，完成后过其 Code Review Checklist。
- subprocess 一律 argv-only；不引入 `shell=True` / `create_subprocess_shell`。
- 不改动 canonical schema（Pydantic/zod 契约字段）；本计划唯一的 Python 行为改动是 Task 11 的一条用户文案。
- UI 文案用英文（现有 UI 语言）；站点文档中英双份同步；代码注释英文。
- 成员身份的 localStorage 用法是既有设计（key `micro-eval:member-name`）；`grep localStorage` 是 review 信号非红线，新增用法必须集中在 Task 1 的单一工具模块。
- 每个任务结束运行该任务的验证命令并 commit（英文 message）；不 push。
- 行号为 2026-07-02 快照，编辑前先 Read 目标文件核对。

## 现状事实（执行者以此为准，来源为已验证的代码勘察）

- `serve` 启动链：`src/micro_eval/cli/serve.py` —— `.next` 缺失时 `npm run build`（第 55–60 行，**构建环境未注入 server 变量**）；`next start` 环境注入 `MICRO_EVAL_SERVER_MODE=true`、`MICRO_EVAL_DATA_ROOT`（第 63–75 行）。
- server 模式判定：`ui/src/lib/server-mode.ts` 读 `process.env.MICRO_EVAL_SERVER_MODE`。
- 静态固化问题页：`ui/src/app/workspaces/page.tsx`（列表冻结）、`ui/src/app/queue/page.tsx`、`ui/src/app/templates/page.tsx`（顶部 `isServerMode()` 不满足即 `notFound()`，均无 `dynamic` 导出）。`ui/src/app/templates/[id]/page.tsx` 同一家族，一并处理。
- 表单 bug：`ui/src/app/workspaces/new/page.tsx` 第 45–60 行——成员名写 localStorage 后放进请求体 `owner`，请求头缺 `X-Micro-Eval-Member`。
- 写请求校验：`ui/src/lib/server-validation.ts` 第 8、24 行。
- 空壳按钮：`ui/src/app/workspace/[id]/page.tsx` 第 71 行 `onClick={undefined}`；完整组件 `ui/src/components/RunEnqueueButton.tsx`（第 25 行已正确发头）全仓库零引用。
- 产物链接：`ui/src/components/CellDetail.tsx` 第 54–57 行附近以 `/run/{runId}/artifact/{artifactId}` 生成；workspace 作用域 API **已存在**：`ui/src/app/api/workspaces/[id]/runs/[runId]/artifacts/`。
- 全局布局：`ui/src/app/layout.tsx` 无任何导航。
- 内部代号文案：`src/micro_eval/decision/summary.py:38`
  `recommended = "review evidence and complete P0-b comparability gate"`；
  断言它的测试：`tests/unit/test_p0b_decision.py`（golden fixture 不含此串）。
- workspace 创建：`src/micro_eval/server/workspace.py` 第 52–71 行（`mkdir` 后逐项 `copytree`，无异常回滚）。
- 模板打包：`src/micro_eval/server/template.py`（create 与 update 两处 copytree/copy2，无排除规则；symlink 防护属安全审计 F4，修复时同点合并）。
- 演示资产：`examples/agent-codefix-showdown/eval.mock.yaml` 为 deterministic mock 配置（秒级、零 API 成本）。

---

## 批次 1：旅程接通（A4 → A5 → A2/A3 → A1 → A6）

### Task 1: 成员身份共享工具模块

**Files:**
- Create: `ui/src/lib/member-identity.ts`
- Test: `ui/src/lib/__tests__/member-identity.test.ts`

**Interfaces:**
- Produces: `MEMBER_NAME_KEY: string`；`getMemberName(): string`（未设置返回 `""`）；`setMemberName(name: string): void`（trim 后写入，空串则移除 key）。后续 Task 2/3/13 均从此模块取身份，不得再散落 `localStorage.getItem` 调用。

- [ ] **Step 1: 实现模块**

```ts
// ui/src/lib/member-identity.ts
// Single source for the member identity stored in the browser.
// Server-mode write APIs require this value in the X-Micro-Eval-Member header.
export const MEMBER_NAME_KEY = "micro-eval:member-name";

export function getMemberName(): string {
  if (typeof window === "undefined") return "";
  return (window.localStorage.getItem(MEMBER_NAME_KEY) ?? "").trim();
}

export function setMemberName(name: string): void {
  if (typeof window === "undefined") return;
  const trimmed = name.trim();
  if (trimmed) window.localStorage.setItem(MEMBER_NAME_KEY, trimmed);
  else window.localStorage.removeItem(MEMBER_NAME_KEY);
}
```

- [ ] **Step 2: 验收测试（实现后补，非 TDD）**——覆盖：读空、写读回、trim、空串移除、SSR（`window` 缺失）不抛错。用 vitest 的 jsdom 环境。
- [ ] **Step 3: 验证** `cd ui && npx vitest run src/lib/__tests__/member-identity.test.ts` 全绿。
- [ ] **Step 4: Commit** `fix(ui): add single-source member identity util (journey A4/A5 prep)`

### Task 2: A4 修复建 workspace 表单

**Files:**
- Modify: `ui/src/app/workspaces/new/page.tsx:45-60`

**Interfaces:**
- Consumes: Task 1 的 `getMemberName`/`setMemberName`。

- [ ] **Step 1: 改提交逻辑**——名字必填（为空时前端阻止提交并提示 "Please enter your name — it is recorded as the workspace owner."）；提交时同时发头与体：

```ts
setMemberName(memberName);           // persist via shared util
const res = await fetch("/api/workspaces", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Micro-Eval-Member": memberName.trim(),
  },
  body: JSON.stringify({ name, description: description || undefined, owner: memberName.trim() }),
});
```

页面挂载时用 `getMemberName()` 预填；替换文件内原有的直接 `localStorage` 读写。

- [ ] **Step 2: 错误文案人性化**——API 错误码到用户文案的映射（至少覆盖 400 身份头缺失 → "Please enter your name first."），不再透传 "valid X-Micro-Eval-Member header required"。
- [ ] **Step 3: 手动验证**（`micro-eval serve` + 浏览器）：填表创建成功并跳转；名字留空被前端拦截。
- [ ] **Step 4: Commit** `fix(ui): send member header from workspace creation form (A4)`

### Task 3: A5 接通 Enqueue Run 按钮

**Files:**
- Modify: `ui/src/components/RunEnqueueButton.tsx`
- Modify: `ui/src/app/workspace/[id]/page.tsx:60-76`（空壳按钮段）

- [ ] **Step 1: 组件自取身份**——`memberName` prop 改为可选；内部用 `getMemberName()`（`useState`+`useEffect` 挂载后读取）。名字为空时点击不发请求，展示内联提示 "Set your name first" 并提供输入框即时保存（`setMemberName`）后重试。
- [ ] **Step 2: 替换空壳**——workspace 页删除 `onClick={undefined}` 的 `<button>`，渲染 `<RunEnqueueButton workspaceId={id} />`。
- [ ] **Step 3: 验收测试**——为组件补 vitest（mock fetch：成功路径断言请求头含 `X-Micro-Eval-Member`；失败路径断言错误文案渲染）。
- [ ] **Step 4: 手动验证**：点击按钮 → `sqlite3 <data-root>/queue.db "select member,status from jobs"` 出现正确归属的新 job；页面跳转或刷新。
- [ ] **Step 5: Commit** `fix(ui): wire RunEnqueueButton into workspace page (A5)`

### Task 4: A2/A3 server 页面动态渲染 + serve 构建环境

**Files:**
- Modify: `ui/src/app/workspaces/page.tsx`、`ui/src/app/queue/page.tsx`、`ui/src/app/templates/page.tsx`、`ui/src/app/templates/[id]/page.tsx`、`ui/src/app/workspaces/new/page.tsx`
- Modify: `src/micro_eval/cli/serve.py:55-60`

- [ ] **Step 1: 五个页面文件顶部（import 之后）各加一行**：

```ts
export const dynamic = "force-dynamic";
```

- [ ] **Step 2: serve 构建注入变量**——`npm run build` 的 `subprocess.run` 增加 `env={**os.environ, "MICRO_EVAL_SERVER_MODE": "true", "MICRO_EVAL_DATA_ROOT": str(data_root)}`（与 `next start` 的 env 结构一致；双保障：动态渲染后构建期判定不再致命，但保持两侧一致避免回归）。
- [ ] **Step 3: 验证**——`cd ui && npm run build`（**不设**环境变量）后 `uv run micro-eval serve`：`curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/queue` 与 `/templates` 均为 200；建一个 workspace 后刷新 `/workspaces` 立即可见。构建输出中上述页面标记为 `ƒ`（Dynamic）。
- [ ] **Step 4: Commit** `fix(ui): force dynamic rendering for server-mode pages; build with server env (A2/A3)`

### Task 5: A1 server 模式着陆与全局导航

**Files:**
- Create: `ui/src/components/ServerNav.tsx`
- Modify: `ui/src/app/layout.tsx`
- Modify: `ui/src/app/page.tsx`

- [ ] **Step 1: 首页重定向**——`page.tsx` 顶部：

```ts
import { redirect } from "next/navigation";
import { isServerMode } from "@/lib/server-mode";
// inside the (server) component, before existing rendering:
if (isServerMode()) redirect("/workspaces");
```

- [ ] **Step 2: ServerNav 组件**（服务端组件）——横向导航：Workspaces `/workspaces`、Queue `/queue`、Templates `/templates`，右侧留身份插槽（Task 13 填充）。视觉沿用现有 banner 的暗色风格。
- [ ] **Step 3: layout 挂载**——`layout.tsx` 的 banner 内 `{isServerMode() && <ServerNav />}`。
- [ ] **Step 4: 验证**：server 模式访问 `/` 落到 `/workspaces`；三页面经导航可达；**单机模式**（`cd ui && npm run dev`，不设变量）首页行为不变、无导航。
- [ ] **Step 5: Commit** `feat(ui): server-mode landing redirect and global nav (A1)`

### Task 6: A6 产物链接按作用域生成

**Files:**
- Modify: `ui/src/components/CellDetail.tsx`
- Modify: 两处调用方——`grep -rn "CellDetail" ui/src/app | grep -v api` 确认（预期：`app/run/[id]/page.tsx` 与 `app/workspace/[id]/run/[runId]/page.tsx`）。

- [ ] **Step 1: 组件加 prop**——`artifactBasePath?: string`，默认值保持现状 `` `/run/${run.run_id}/artifact` ``；链接改为 `` `${artifactBasePath}/${encodeURIComponent(artifactId)}` ``。
- [ ] **Step 2: workspace 调用方传值**——`` artifactBasePath={`/workspace/${workspaceId}/run/${runId}/artifact`} ``。
- [ ] **Step 3: 补 workspace 作用域产物页**——若 `ui/src/app/workspace/[id]/run/[runId]/artifact/[artifactId]/page.tsx` 不存在则新建：复用项目作用域产物页的渲染，数据改走已存在的 `api/workspaces/[id]/runs/[runId]/artifacts/` 路由（先 Read 该 API 确认响应形状）。
- [ ] **Step 4: 验证**：server 模式从矩阵格子证据点开 stdout/stderr 均 200 且内容可见；单机模式（`examples/run-example.py` 产物 + `micro-eval ui`）原链接不回归。
- [ ] **Step 5: Commit** `fix(ui): scope artifact links to workspace routes in server mode (A6)`

---

## 批次 2：可靠性（B7–B10；动手前读 security-guidelines）

### Task 7: B7 serve 构建新鲜度检测

**Files:**
- Modify: `src/micro_eval/cli/serve.py`

- [ ] **Step 1: 启动前检查**——`.next/BUILD_ID` 存在时，比较其 mtime 与 `ui/src/**` 最新 mtime（`max(p.stat().st_mtime for p in ui_src.rglob("*") if p.is_file())`）；构建旧于源码时 `typer.echo` 警告并提示 `cd ui && npm run build`（不自动重建，保持启动可预期；`.next` 缺失时的自动构建路径已由 Task 4 注入变量）。
- [ ] **Step 2: 验证**：`touch ui/src/app/page.tsx` 后启动 serve 出现警告；重建后启动无警告。
- [ ] **Step 3: Commit** `fix(serve): warn when Next.js build is older than ui sources (B7)`

### Task 8: B8 进程组终止与 stale pid 接管

**Files:**
- Modify: `src/micro_eval/cli/serve.py`
- Modify: `src/micro_eval/server/worker.py`（pid 文件处理段，先 Read 定位）

- [ ] **Step 1: serve 信号处理**——注册 SIGTERM/SIGINT handler：终止 `next_proc` 与 `worker_proc`（`terminate()` → 超时 `kill()`），已有 finally 清理路径合并复用；子进程创建保持 argv-only 不变。
- [ ] **Step 2: worker stale pid**——启动读到 `worker.pid` 时 `os.kill(pid, 0)` 探活（`ProcessLookupError` 即 stale）：stale 则记日志、删文件、正常接管；存活则维持现有拒绝行为。
- [ ] **Step 3: 验证**：`kill <serve-pid>` 后 `lsof -i :<port>` 为空、无 worker 进程、pid 文件消失；随即重启成功。手工放置指向不存在 PID 的 `worker.pid` 后启动成功。
- [ ] **Step 4: 单测**——worker stale-pid 分支补 pytest（tmp_path 伪造 pid 文件）。
- [ ] **Step 5: Commit** `fix(server): terminate child processes on signal; take over stale worker.pid (B8)`

### Task 9: B9 模板打包排除规则（与安全审计 F4 同点合并）

**Files:**
- Modify: `src/micro_eval/server/template.py`（create 与 update 两处复制逻辑）
- Test: `tests/unit/test_template_registry.py`（如无则新建，先 `ls tests/unit | grep template` 核对）

- [ ] **Step 1: 排除常量**：

```python
TEMPLATE_EXCLUDES = shutil.ignore_patterns(
    ".micro-eval", ".git", "__pycache__", ".next",
    "node_modules", "report.html", ".DS_Store",
)
```

两处 `shutil.copytree(..., ignore=TEMPLATE_EXCLUDES, symlinks=False)`；逐文件路径增加 symlink/non-regular 跳过（F4：`Path.is_symlink()` 检查后跳过并记 warning，不 follow）。

- [ ] **Step 2: 验证**——pytest：以含 `.micro-eval/`、symlink 的源目录注册模板，断言产物中两者均不存在；`uv run pytest tests/unit -k template -q`。
- [ ] **Step 3: Commit** `fix(server): exclude runtime artifacts and symlinks from template packaging (B9, audit F4)`

### Task 10: B10 workspace 创建失败回滚与可读错误

**Files:**
- Modify: `src/micro_eval/server/workspace.py:52-71`
- Modify: `src/micro_eval/cli/workspace.py`（错误展示，先 Read 定位 create 命令的异常处理）

- [ ] **Step 1: 回滚**——创建流程包 try/except：任何异常时 `shutil.rmtree(ws_dir, ignore_errors=True)` 后抛领域错误（沿用 server 层既有错误类型；如无则 `WorkspaceError`），message 说明冲突文件与建议（"template contains .micro-eval/ — re-register it after upgrading (B9 fixes packaging)"）。
- [ ] **Step 2: CLI 出口**——create 命令捕获领域错误，打印单行错误退出码 1，不再露 traceback。
- [ ] **Step 3: 验证**——pytest：用带 `.micro-eval/` 的旧模板触发失败，断言 workspaces 目录无残留、错误信息可读；`uv run pytest tests/unit -k workspace -q`。
- [ ] **Step 4: Commit** `fix(server): roll back partial workspace on create failure with readable error (B10)`

---

## 批次 3：引导与说明（C11–C15）

### Task 11: C12 决策文案去内部代号 + 决策卡片 tooltip

**Files:**
- Modify: `src/micro_eval/decision/summary.py:38`
- Modify: `tests/unit/test_p0b_decision.py`（该字符串的断言同步更新）
- Modify: `ui/src/components/DecisionSummary.tsx`（先 Read 确认卡片字段渲染位置）

- [ ] **Step 1: Python 文案**：

```python
recommended = "review the evidence for each cell and confirm the runs are comparable before acting"
```

- [ ] **Step 2: 同步测试断言**；确认 golden fixture 无此串（已核实），运行 `uv run pytest tests/unit/test_p0b_decision.py tests/contract -q` 守护契约。
- [ ] **Step 3: tooltip**——决策卡片字段加 `title` 提示（服务端组件用原生 title 即可，勿引入新依赖）：Decision（"Overall verdict…"）、Confidence、Evidence refs（"Number of evidence items backing this decision"）、Replay digest（"Fingerprint of replay-affecting inputs; equal digests mean comparable runs"）、Snapshot gate、low sample（"Fewer than 3 repetitions — treat differences as noise until rerun"）。措辞与 `site/guide/design-system.md` 术语对齐。
- [ ] **Step 4: 验证**——UI 全文 `grep -rn "P0-" ui/src --include="*.tsx"` 零命中；`uv run pytest -q` 与 `npx vitest run` 全绿。
- [ ] **Step 5: Commit** `fix(decision): user-facing recommended action; add decision card tooltips (C12)`

### Task 12: C13 失败分层一行解释

**Files:**
- Modify: `ui/src/components/CellDetail.tsx`

- [ ] **Step 1: 结论行**——证据区顶部根据 cell 状态与 evidence 组合渲染一句话（纯前端映射函数，放组件文件内）：进程 pass + validation warning/fail → "Process exited normally, but the output failed validation (expected text missing)."；timeout → "The agent hit the per-cell timeout."；crash/非零退出 → "The agent process exited with an error (exit code N)."；全部通过 → 不渲染。
- [ ] **Step 2: 验证**——vitest 快照/断言各分支文案；手动打开 alice run 复核 claude-code 格子第一行可读。
- [ ] **Step 3: Commit** `feat(ui): plain-language failure explanation per cell (C13)`

### Task 13: C11 全局身份组件

**Files:**
- Create: `ui/src/components/MemberIdentity.tsx`（client 组件）
- Modify: `ui/src/components/ServerNav.tsx`（Task 5 预留的插槽）

- [ ] **Step 1: 组件**——展示当前 `getMemberName()`（空则 "Set your name"），点击展开输入框即时 `setMemberName` 保存；样式复用 `MemberBadge` 的 badge 视觉。
- [ ] **Step 2: 验证**——任意 server 页面右上角可见/可改身份；改名后 Task 3 的 enqueue 以新名字入队（sqlite 查 member 字段）。
- [ ] **Step 3: Commit** `feat(ui): persistent member identity widget in server nav (C11)`

### Task 14: C14 enqueue 确认卡片 + 出厂演示模板

**Files:**
- Create: `ui/src/app/api/workspaces/[id]/plan-summary/route.ts`
- Modify: `ui/src/components/RunEnqueueButton.tsx`
- Modify: `src/micro_eval/cli/serve.py`（首次初始化种子模板）
- Create: `src/micro_eval/server/seed_template/`（打包进 wheel 的演示模板源，内容取自 `examples/agent-codefix-showdown` 的 mock 配置：`eval.mock.yaml` 改名 `eval.yaml` + `tasks/` + `workspace/`，**不含真实 agent 配置**）

- [ ] **Step 1: plan-summary API**——GET：读 workspace 的 `eval.yaml`，经既有 `build_run_plan` 路径（与 queue 的 `queryQueue` 同款 Python 桥接）返回 `{tasks, configurations, repetitions, total_cells, agent_commands: string[]}`；只读、无身份头要求。
- [ ] **Step 2: 确认卡片**——`RunEnqueueButton` 点击后先取 plan-summary 展示（N tasks × M configurations × R reps = K cells；agent 命令列表），"Confirm & Enqueue" 才真正 POST；摘要获取失败时降级为现行为并提示无法预览。
- [ ] **Step 3: 种子模板**——serve 首次初始化 data root 时若模板注册表为空，从打包资源复制 `seed_template` 注册为 `id=demo-codefix`、name "Demo: Codefix Showdown (mock agents, free)"；`pyproject.toml` 确认打包包含该目录（`[tool.hatch.build]` 数据文件配置，先 Read 现状）。
- [ ] **Step 4: 验证**——新 data root 起 serve：`micro-eval template list` 见 demo 模板；浏览器从模板建 workspace → enqueue 出确认卡片（1 task × 2 configs × 1 rep）→ 确认后 mock run 秒级完成且零外部调用。
- [ ] **Step 5: Commit** `feat(server): enqueue confirmation with plan summary; seed demo template (C14)`

### Task 15: C15 文档命令修正

**Files:**
- Modify: `site/guide/team-server.md` + `site/zh/guide/team-server.md`

- [ ] **Step 1: 更正示例**为 `micro-eval template create ./my-eval-config --id baseline-eval --name "Baseline Eval"`；顺带把本计划新增行为写进指南：serve 构建警告（Task 7）、确认卡片与 demo 模板（Task 14）、成员身份组件（Task 13）。中英同步。
- [ ] **Step 2: 验证**——指南中每条命令逐条对 `--help` 核对执行。
- [ ] **Step 3: Commit** `docs(site): correct template create syntax; document journey features (C15)`

### Task 16: 总验收——重跑 10 分钟旅程

- [ ] **Step 1: 全量回归**——`uv run pytest -q`、`cd ui && npm run lint && npm run build && npx vitest run`、`uv run python examples/run-example.py`、`grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples || true`。
- [ ] **Step 2: 旅程实测**——干净 data root + 干净浏览器 profile，按 bug report §1 总验收标准走完整旅程并计时；每一步截图存 `docs/analysis/` 附件目录。
- [ ] **Step 3: 安全清单**——过 `docs/engineering/security-guidelines.md` Code Review Checklist，交付说明中写明 secrets redaction / workspace boundary / shell interpolation 三项处理方式。
- [ ] **Step 4: 收尾文档**——bug report 15 项逐条标注 resolved（附验证证据）；`docs/analysis/2026-07-02-team-server-member-journey-gaps.md` 状态改 resolved；CHANGELOG 新条目（版本号 bump 与发布另行走 release 流程，不在本计划内）。
- [ ] **Step 5: Commit** `docs: mark journey findings resolved with walkthrough evidence`

---

## 明确不在本计划范围

- 安全审计 F1（Host 校验）、F2（bridge try/finally）、F3（Content-Type 强制）、F5（worker ID 校验）——独立排期（F4 已并入 Task 9）。
- 版本号 bump、release、push——走 `docs/engineering/release-process.md`。
- 首次打开的分步引导 tour（用户目标之一）——依赖本计划全部完成后的稳定界面，建议作为下一个计划单独设计（含视觉方案评审）。

## Self-Review 记录

- 覆盖核查：bug report A1–A6 → Task 2–6 与 Task 5；B7–B10 → Task 7–10；C11–C15 → Task 11–15；总验收 → Task 16。F4 并入 Task 9 有明确标注。15/15 全覆盖。
- 占位符核查：所有代码步骤给出可执行片段或精确定位 + 核对命令；无 TBD。
- 接口一致性：`member-identity.ts` 的三个导出在 Task 2/3/13 引用名一致；`artifactBasePath` prop 在 Task 6 内自洽；`TEMPLATE_EXCLUDES` 仅 Task 9 使用。
