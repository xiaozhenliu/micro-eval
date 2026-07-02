---
title: Team Server 新成员旅程实测——缺口清单
doc_type: analysis
status: active
created_at: 2026-07-02T16:10+08:00
updated_at: 2026-07-02T16:10+08:00
owner: micro-eval maintainers
source_of_truth: true
tags:
  - team-server
  - user-journey
  - ux
related:
  - docs/superpowers/specs/2026-06-19-team-server-design.md
  - docs/security/2026-06-20-security-audit.md
  - site/guide/team-server.md
---

# Team Server 新成员旅程实测——缺口清单

## 测试方法

2026-07-02，在干净数据目录（`/tmp/me-journey-server`）上按用户文档架起 Team
Server（`micro-eval serve --port 3210`），然后扮演新成员 alice：只知道服务器
地址，用真实浏览器（Playwright）从零走"表明身份 → 建 workspace → 发起 run →
读懂第一个结果"的完整旅程。所有发现均已在代码中定位到根因。

**验收基准**（对齐产品的 10 分钟成功标准）：新成员拿到 server 地址和一句话说
明，10 分钟内不问任何人，完成第一次评测并读懂结论。

**实测结论：旅程无法在浏览器中完成。** 成员的两个核心动作（建 workspace、发
起 run）在 UI 上均不可用；队列页、模板页、workspace 列表页均处于损坏或冻结状
态。当前 Team Server 实际只能由拥有服务器 shell 权限的人用 CLI 驱动，浏览器
端是不可用的。

## A 类：旅程阻断（成员在浏览器里无法完成的动作）

### A1. 首页是单机版页面，成员无路可走

打开 `http://server:3210/` 看到的是单机版 run 列表页，空状态提示"Run
`micro-eval run` to get started"——对成员这是错误指引（该命令在成员自己电脑
上运行连不到服务器）。页面没有任何指向 workspaces / queue / templates 的导航。
`serve` 已设置 `MICRO_EVAL_SERVER_MODE=true`，但根布局和首页从未消费该标志
（消费者只有 API 路由和 queue 页，见 `ui/src/lib/server-mode.ts` 的引用清单）。

### A2. `/workspaces` 列表页数据被冻结在构建时刻

该页是静态预渲染页（无 `export const dynamic = "force-dynamic"`），
`listWorkspaces()` 在 `next build` 时执行一次后数据固化。实测：创建
workspace 后列表页仍显示 "No workspaces found"。成员永远看不到自己（和同事）
的 workspace，只能靠别人发 URL。

### A3. `/queue` 与 `/templates` 永久 404

两页在服务端组件顶部调用 `isServerMode()`，不满足则 `notFound()`。它们同为
静态预渲染页：`npm run build` 时 `MICRO_EVAL_SERVER_MODE` 未设置，404 被固化
进构建产物，运行时环境变量无法翻案。更关键的是 `serve` 自带的构建路径
（`src/micro_eval/cli/serve.py`：`.next` 不存在时执行 `npm run build`）同样
**没有**在构建环境中设置该变量——即每一台按文档部署的服务器都必然如此。
后果：成员看不到队列（排到第几、谁在跑），也看不到模板库（设计中新人的起步
资产完全不可见）。

### A4. 建 workspace 表单必然提交失败

`ui/src/app/workspaces/new/page.tsx` 把成员名放进请求体（`owner` 字段），只
发 `Content-Type` 头；而 `ui/src/lib/server-validation.ts` 要求所有写请求携
带 `X-Micro-Eval-Member` 头。前后端约定不一致，表单在任何输入下都返回错误，
且错误文案原样展示内部头名："valid X-Micro-Eval-Member header required"。

### A5. "Enqueue Run" 按钮是空壳，真实现是死代码

`ui/src/app/workspace/[id]/page.tsx:71` 的按钮为 `onClick={undefined}`，点击
无任何反应（无请求、无报错、无跳转）。而带加载态、错误提示、正确身份头的完
整组件 `ui/src/components/RunEnqueueButton.tsx` **没有被任何页面引用**。用正
确的头直接调 API（`POST /api/workspaces/{id}/runs/enqueue`）则一切正常——
后端是通的，前端没接上。

### A6. 证据链在最后一跳断裂：产物链接 404

run 结果页 Cell Evidence 中的 stdout/stderr/output 链接指向单机模式路由
`/run/{runId}/artifact/{artifactId}`，而非 workspace 作用域路由。server 模式
下该路由读不到 workspace 数据，实测 404。这违反了产品自己的 Decision
Surface 义务第 2 条（"证据链可导航：decision → task → trace → diff 逐级下钻
不可断链"，unicorn-design §5.8）。

## B 类：可靠性问题（管理员侧，架服务时踩到）

### B7. `serve` 使用过期构建，无任何检测或提示

实测时 `.next` 构建产物是 6 月 15 日的（团队版 6 月 19 日才实现），`serve`
直接端着一个没有任何团队版页面的旧界面上线，全程无警告。`serve` 只检查
`.next` 是否存在，不检查其新旧。

### B8. `serve` 父进程被终止后子进程成为孤儿

对 serve 父进程发 SIGTERM 后，Next.js 子进程继续占用端口、Python worker 继
续持有 `worker.pid`，导致重启报 `EADDRINUSE` + "Another worker is already
running"，需手动清理进程和 pid 文件。文档只写了 Ctrl-C（SIGINT）路径。

### B9. `template create` 不排除运行时产物

把 `examples/agent-codefix-showdown` 注册为模板时，源目录里的 `.micro-eval/`
运行数据和 `report.html` 被原样打进模板。模板应有排除规则（至少
`.micro-eval/`、`report.html`、`.git/`）。

### B10. `workspace create --template` 冲突时崩溃且残留脏数据

用含 `.micro-eval/` 的模板创建 workspace 时抛原始 Python traceback
（`FileExistsError`），且已创建一半的 workspace 目录残留磁盘；该目录不在服
务器索引中，`workspace delete` 报 "not found"，产品自身无法清理，只能手动
`rm -rf`。

## C 类：说明与引导缺失（可用性，对应产品目标）

### C11. 成员身份没有任何界面存在感

全站无身份显示（右上角没有"我是谁"），身份概念只出现在建 workspace 表单的
一行小字里。成员不知道自己的操作以什么身份记录、别人如何看到自己。

### C12. 结果页术语零解释，内部代号泄漏

"Evidence refs 16"、"Replay digest 8cb358027608"、"Snapshot gate"、"low
sample" 均无悬停说明；推荐动作一栏直接显示 "review evidence and complete
**P0-b comparability gate**"——内部里程碑代号出现在成员界面上。

### C13. 失败原因对新人不可读

alice 的第一个 run 里 claude-code 格子显示 fail，点开证据看到的是
`status=pass exit_code=0` + "output missing expected text"（validation
warning）。进程成功但验收失败的分层逻辑没有任何界面解释，新人无法理解"为什
么 exit 0 还是 fail"。

### C14. 一键排队可能直接烧钱，无预警

模板携带的 `eval.yaml` 是真实 agent 配置（claude/codex/openclaw/hermes）。
成员点一下 Enqueue（当它可用时）就会在服务器上调真实 CLI、消耗真实 API 配
额。没有任何"这将运行什么、大约多久、什么成本"的确认步骤。

### C15. 文档命令语法错误

`site/guide/team-server.md`（中英同）写的是 `template create --name X
--source ./dir`：实际 source 是位置参数，`--source` 选项不存在，必填的
`--id` 未提及。照文档敲必报错。

## 产品级修复方向（对应上述缺口）

按"界面结构 / 视觉 / 悬停说明 / 首次旅程"四个方向归纳：

1. **界面结构**：server 模式下提供独立首页与全局导航（Workspaces / Queue /
   Templates / 我的身份），单机版页面不再作为着陆页（修 A1）；所有 server
   模式页面改为动态渲染或运行时判定（修 A2/A3）；产物链接改用 workspace 作
   用域路由（修 A6）；接通 `RunEnqueueButton` 与建 workspace 表单的身份头
   （修 A4/A5）。
2. **视觉**：矩阵/结果页已有基础，重点是失败格子的原因分层展示（进程 vs 验
   收，修 C13）与队列页的状态可视化（依赖 A3 先修）。
3. **悬停说明**：为 Decision / Confidence / Evidence refs / Replay digest /
   Snapshot gate / low sample 配 tooltip；推荐动作文案改为面向用户的语言，
   去除内部代号（修 C12）。
4. **首次旅程**：浏览器首次打开时的引导流程——"设置你的名字 → 从模板创建
   workspace → 预览将运行的配置与预估成本 → 发起第一个 run → 结果页导览"。
   前置条件：模板可在 UI 中浏览与选用（A3）、建 workspace 可用（A4）、
   enqueue 可用（A5）、运行前确认步骤（C14）。另建议服务器出厂自带一个
   deterministic 演示模板（mock agent，零成本、秒级完成），新人第一跑不碰真
   实 API。
5. **可靠性打底**：serve 构建新鲜度检测 + server 模式构建变量（B7/A3 同
   源）；进程组终止与 stale pid 清理（B8）；模板打包排除规则（B9）；创建失
   败的清理与可诊断错误（B10）；文档命令核对（C15）。

## 修复顺序建议

A 类 6 项是"团队版能不能用"的问题，先修；B 类是"架得稳不稳"，随 A 一起修
（B7 与 A3 同根因）；C 类引导优化建立在 A 类修复之上，与安全审计
（`docs/security/2026-06-20-security-audit.md`，5 项未修复）合并排期。全部
完成后重跑本文的 10 分钟旅程作为团队版的完成验收。
