---
title: Team Server 成员旅程实测问题清单
doc_type: analysis
status: active
created_at: 2026-07-02T16:30+08:00
updated_at: 2026-07-02T16:30+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - bug-report
  - team-server
  - ui
  - ux
related:
  - docs/analysis/2026-07-02-team-server-member-journey-gaps.md
  - docs/security/2026-06-20-security-audit.md
  - docs/superpowers/specs/2026-06-19-team-server-design.md
  - site/guide/team-server.md
---

# Team Server 成员旅程实测问题清单

> **来源**：2026-07-02 新成员旅程实测（方法与叙述见
> `docs/analysis/2026-07-02-team-server-member-journey-gaps.md`）。
> 本文将实测发现整理为标准问题清单，供逐项修复与验收。
> 安全审计发现（F1–F5）另见 `docs/security/2026-06-20-security-audit.md`，不在本文重复。

## 1. 范围与验证

在干净数据目录上启动 Team Server，用真实浏览器扮演新成员走完整旅程：

```bash
cd ui && npm run build          # 复现 A2/A3 需以此方式构建（不设 MICRO_EVAL_SERVER_MODE）
uv run micro-eval serve --port 3210 --data-root /tmp/me-journey-server
# 浏览器访问 http://localhost:3210 起，按成员视角操作
```

后端 API 用正确请求头直接调用时全部正常（建 workspace、enqueue、执行、出矩阵、
证据均可用）；以下问题集中在 UI 接线、页面构建方式与进程管理。

**总验收标准（全清单共享）**：修复完成后，新成员拿到 server 地址，在 10 分钟内
不借助任何 CLI 与他人协助，于浏览器中完成：表明身份 → 从模板创建 workspace →
发起一次 run → 在队列中看到进度 → 打开结果矩阵并从任一格子下钻到原始产物。

---

## 2. 问题 A1：server 模式首页仍是单机版页面，成员无入口

**严重度：严重**

### 现象

打开 `http://server:3210/` 显示单机版 run 列表页，空状态提示 "Run
`micro-eval run` to get started"（对成员是错误指引），页面无任何指向
workspaces / queue / templates 的导航。

### 关键证据

- `src/micro_eval/cli/serve.py:65` 已设置 `MICRO_EVAL_SERVER_MODE=true`；
- 消费该标志的只有 API 路由与 `ui/src/app/queue/page.tsx`（grep
  `isServerMode` 结果），根布局与首页 `ui/src/app/page.tsx` 从未判断 server 模式。

### 影响

成员着陆即死路，必须由他人口头告知深层 URL。

### 建议修复

server 模式下首页重定向到 `/workspaces`（或渲染 server 专属着陆页），全局导航
增加 Workspaces / Queue / Templates / 成员身份入口；单机版提示语不在 server
模式渲染。

### 验收标准

server 模式访问 `/` 不再出现 `micro-eval run` 提示；导航可达三个 server 页面。

## 3. 问题 A2：`/workspaces` 列表数据冻结在构建时刻

**严重度：阻断**

### 现象

创建 workspace 成功后，`/workspaces` 仍显示 "No workspaces found"（curl 与浏
览器一致）。

### 关键证据

- `ui/src/app/workspaces/page.tsx` 为静态预渲染页（构建输出标记 `○`，无
  `export const dynamic = "force-dynamic"`），`listWorkspaces()` 仅在
  `next build` 时执行一次，结果固化进 HTML。

### 影响

成员永远看不到自己与同事的 workspace；列表页作为成员的主导航完全失效。

### 建议修复

为所有读实时数据的 server 模式页面声明 `export const dynamic =
"force-dynamic"`（或改用运行时数据获取），并在 CI 增加"构建产物中 server 页
面不得为静态"的检查。

### 验收标准

创建 workspace 后刷新 `/workspaces` 立即可见新条目。

## 4. 问题 A3：`/queue` 与 `/templates` 永久 404

**严重度：阻断**

### 现象

两页返回 404。重建 UI 后依旧；每台按文档部署的服务器均必然复现。

### 关键证据

- `ui/src/app/queue/page.tsx` 顶部 `isServerMode()` 不满足即 `notFound()`；
  页面为静态预渲染，`npm run build` 时环境变量未设置，404 固化进构建产物；
- `src/micro_eval/cli/serve.py:55-60`：serve 自带的构建路径（`.next` 缺失时
  执行 `npm run build`）同样未在构建环境注入 `MICRO_EVAL_SERVER_MODE`（该变
  量只传给了 `next start`，见 serve.py:63-67）。

### 影响

成员看不到队列（排队位置、谁在运行），模板库对浏览器完全不可见——设计中新人
的起步资产无法被发现。

### 建议修复

与 A2 同源：页面改为动态渲染；serve 的构建命令注入 server 模式变量；或将
server 模式判定改为运行时请求级判断（不依赖构建期环境）。

### 验收标准

server 模式下 `/queue`、`/templates` 返回 200 并显示实时数据；用
`npm run build`（不设变量）构建后经 `micro-eval serve` 启动仍满足前句。

## 5. 问题 A4：建 workspace 表单必然提交失败（身份头约定不一致）

**严重度：阻断**

### 现象

表单填写任意合法内容提交，均报错 "valid X-Micro-Eval-Member header
required"，无法创建 workspace。

### 关键证据

- `ui/src/app/workspaces/new/page.tsx:55-60`：成员名放入请求体 `owner` 字段，
  请求头只有 `Content-Type`；
- `ui/src/lib/server-validation.ts:8,24`：所有写请求要求
  `X-Micro-Eval-Member` 头，缺失即拒绝。

### 影响

成员无法从浏览器创建 workspace——旅程第一步即中断；错误文案将内部 HTTP 头名
直接暴露给最终用户。

### 建议修复

表单提交时把成员名同时写入 `X-Micro-Eval-Member` 头（与
`RunEnqueueButton.tsx:25` 的正确做法一致）；校验失败的用户可见文案改为面向用
户的语言（如"请先填写你的名字"）。

### 验收标准

浏览器中填表创建 workspace 成功并跳转到新 workspace 页；异常路径文案不含内部
头名。

## 6. 问题 A5："Enqueue Run" 按钮为空壳，真实现是死代码

**严重度：阻断**

### 现象

workspace 页点击 "Enqueue Run" 无任何反应：无网络请求、无错误提示、无跳转；
队列（`queue.db` jobs 表）无新增记录。

### 关键证据

- `ui/src/app/workspace/[id]/page.tsx:71`：`onClick={undefined}`；
- `ui/src/components/RunEnqueueButton.tsx`：带加载态、错误展示与正确身份头的
  完整实现，但全仓库无任何 import（grep 证实）。

### 影响

成员无法从浏览器发起 run——旅程核心动作不可用。用正确头直接调
`POST /api/workspaces/{id}/runs/enqueue` 则正常，证明仅前端未接线。

### 建议修复

workspace 页改用 `RunEnqueueButton` 组件，成员名来源与 A4 统一（localStorage
`micro-eval:member-name`）；补充"未设置名字时先引导填写"的分支。

### 验收标准

浏览器点击按钮 → 队列出现新 job 且归属正确成员 → 页面跳转到 job/run 视图；
名字未设置时给出引导而非静默失败。

## 7. 问题 A6：结果页产物链接使用单机路由，server 模式下 404

**严重度：严重**

### 现象

run 结果页 Cell Evidence 中 stdout/stderr/output 链接形如
`/run/{runId}/artifact/{artifactId}`，点击 404。

### 关键证据

- 实测链接 URL 与 `curl` 404（见 analysis 文档 A6 节）；
- workspace 作用域存在对应 API：
  `ui/src/app/api/workspaces/[id]/runs/[runId]/cells/[cellId]/...`，但渲染证
  据的组件在 server 模式下仍生成 project 作用域链接。

### 影响

证据链最后一跳断裂，违反 Decision Surface 义务第 2 条（unicorn-design §5.8
"证据链可导航……不可断链"）。成员无法核对失败原因的原始输出。

### 建议修复

证据/产物链接组件按运行模式生成 workspace 作用域 URL；补一条 server 模式 E2E
断言"从矩阵格子可下钻到产物内容"。

### 验收标准

server 模式下从任一格子的证据链接点开能看到产物内容（或明确的脱敏占位）。

## 8. 问题 B7：serve 使用过期构建且无任何提示

**严重度：严重**

### 现象

`.next` 为 6 月 15 日构建（早于 Team Server 实现），`micro-eval serve` 直接
启动旧界面上线，全程无警告——表现为整套 server 页面"不存在"。

### 关键证据

- `src/micro_eval/cli/serve.py:55-60`：仅检查 `.next` 目录是否存在，不校验其
  新鲜度或是否包含 server 页面。

### 建议修复

serve 启动时校验构建产物（如比对 BUILD_ID 时间与源码最新 mtime，或探测
`.next` 中 server 路由是否存在），过期则提示并可选自动重建（构建时注入
server 模式变量，与 A3 联动）。

### 验收标准

用旧构建启动 serve 时终端出现明确警告或自动重建；启动后 `/workspaces` 可用。

## 9. 问题 B8：serve 父进程终止后子进程成孤儿，阻塞重启

**严重度：中等**

### 现象

对 serve 父进程发 SIGTERM 后：Next.js 子进程继续占用端口（`EADDRINUSE`），
worker 继续运行且 `worker.pid` 残留（"Another worker is already running"），
需手动 kill 进程并删 pid 文件才能重启。

### 建议修复

serve 以进程组管理子进程并在 SIGTERM/SIGINT 统一传递终止；worker 启动时检测
stale pid（进程不存在则清理接管）。

### 验收标准

`kill <serve-pid>` 后端口释放、worker 退出、pid 文件清理；立即重启成功。

## 10. 问题 B9：template create 打包运行时产物

**严重度：中等**

### 现象

以跑过 example smoke 的目录为源注册模板，`.micro-eval/`（运行数据）与
`report.html` 被原样打进模板。

### 关键证据

- `/tmp/me-journey-server/templates/codefix-demo/` 实测含 `.micro-eval/`、
  `report.html`；
- `src/micro_eval/server/template.py` 的 copytree 无排除规则（与安全审计 F4
  同一代码位置，F4 关注 symlink，本条关注运行时产物）。

### 建议修复

模板打包排除 `.micro-eval/`、`report.html`、`.git/` 等运行时/仓库目录（与
F4 的 symlink 防护一并修）。

### 验收标准

以脏目录为源注册模板后，模板内容不含上述目录/文件。

## 11. 问题 B10：workspace create --template 冲突时崩溃并残留不可删除的脏目录

**严重度：中等**

### 现象

用含 `.micro-eval/` 的模板创建 workspace：抛原始 `FileExistsError` traceback
（目标 `.micro-eval` 已预创建，copytree 冲突）；已建一半的 workspace 目录残
留磁盘，但不在服务器索引中，`workspace delete` 报 "workspace not found"，产
品自身无法清理。

### 建议修复

创建流程 try/except 中失败即回滚删除半成品目录，并给出可读错误；delete 支持
按目录名清理索引外残留（或提供 `workspace prune`）。B9 修复后此触发路径消失，
但回滚逻辑仍应存在（其他 IO 失败同样会触发）。

### 验收标准

人为制造创建失败后：磁盘无残留目录；错误信息为一句可读中文/英文而非 traceback。

## 12. 问题 C11：成员身份无界面存在感

**严重度：中等**

### 现象

全站无"当前身份"显示；身份概念只出现在建 workspace 表单的一行小字
（"Stored locally and used as workspace owner"）。成员不知道操作以什么身份记
录、去哪里修改。

### 建议修复

全局导航常驻身份组件（读写 localStorage `micro-eval:member-name`，未设置时引
导填写）；所有写操作从同一来源取身份（与 A4/A5 统一）。

### 验收标准

任意页面可见并可修改当前身份；未设置身份时首次写操作触发引导而非报错。

## 13. 问题 C12：结果页术语无解释，内部代号泄漏到成员界面

**严重度：中等**

### 现象

"Evidence refs 16"、"Replay digest 8cb358027608"、"Snapshot gate"、"low
sample" 均无任何解释；推荐动作一栏显示 "review evidence and complete
**P0-b comparability gate**"——内部里程碑代号直接面向成员。

### 建议修复

为决策卡片各字段与 caveat 配 tooltip（鼠标悬停展示一句话解释——对应产品目标
中的悬停说明）；推荐动作文案改为用户语言，建立"界面文案不得包含内部代号"的
review 规则。

### 验收标准

结果页每个术语有悬停说明；全站 grep 无 `P0-`/内部里程碑代号出现在 UI 文案。

## 14. 问题 C13：失败原因分层对新成员不可读

**严重度：中等**

### 现象

格子显示 fail，点开证据却见 `status=pass exit_code=0` 与 "output missing
expected text"（validation warning）。"进程成功但验收失败"的分层无界面解释，
新成员无法回答"为什么 exit 0 还是 fail"。

### 建议修复

格子/证据区顶部给出一行结论式解释（如"进程正常退出，但输出未通过验收断言
（缺少期望文本）"），分层术语配 tooltip；失败模式枚举
（validation/timeout/crash/…）映射为用户可读描述。

### 验收标准

任一失败格子点开后，第一行即可读懂"哪一层失败、为什么"。

## 15. 问题 C14：一键排队可运行真实 agent，无成本预警

**严重度：严重**

### 现象

模板携带的 `eval.yaml` 为真实 agent 配置（claude/codex/openclaw/hermes）。
enqueue 无任何确认步骤——成员一次点击即在服务器上调用真实 CLI、消耗真实 API
配额与费用，且不知道将运行什么、预计多久。

### 建议修复

enqueue 前显示确认卡片：将运行的 tasks × configurations × repetitions 规模、
涉及的 agent 命令、（有历史数据时）上次耗时/成本参考；服务器出厂内置一个
deterministic 演示模板（mock agent，秒级、零成本），文档与首次引导默认指向它。

### 验收标准

enqueue 必经确认步骤并展示运行规模；新装服务器自带可直接运行的演示模板。

## 16. 问题 C15：文档 template create 命令语法错误

**严重度：轻微**

### 现象

`site/guide/team-server.md`（中英同）示例为
`micro-eval template create --name baseline-eval --source ./my-eval-config/`：
实际 `source_dir` 是位置参数（`--source` 选项不存在），必填的 `--id` 未提及。
照文档执行必报错。

### 建议修复

更正为 `micro-eval template create ./my-eval-config --id baseline-eval --name
"Baseline Eval"`（中英两份同步）；将"文档命令与 `--help` 输出核对"纳入
release 前检查。

### 验收标准

按文档命令逐条执行全部成功。

---

## 17. 修复顺序建议

1. **第一批（旅程接通，阻断项）**：A4、A5（前端接线，小改动）→ A2、A3（页面
   渲染模式 + serve 构建变量，同根因）→ A1（导航/着陆）→ A6（链接作用域）。
2. **第二批（可靠性）**：B7（与 A3 联动）、B8、B9+B10（与安全审计 F4 合并修）。
3. **第三批（引导与说明）**：C11 → C14 → C12、C13 → C15（文档随第一批顺手修
   亦可）。
4. 与 `docs/security/2026-06-20-security-audit.md` 的 F1–F5 合并排期；全部完
   成后重跑 §1 的 10 分钟旅程作为团队版完成验收。
