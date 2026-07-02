---
title: "Team Server：micro-eval 多成员共享 Server 架构设计"
date: 2026-06-19
updated: 2026-07-02
status: implemented
type: feature-spec
codename: TeamServer
tags:
  - team
  - server
  - workspace
  - queue
  - template
  - v0.4
relates:
  - 2026-06-02-unicorn-design.md
  - 2026-06-15-global-registry-design.md
  - 2026-06-02-mvp-profile.md
---

# Team Server：micro-eval 多成员共享 Server 架构设计

**代号**: TeamServer
**日期**: 2026-06-19
**状态**: Implemented（已随 v0.4.0 交付，2026-06-19）
**基于**: 方案 A（Next.js server + 现有引擎作 worker）
**前置**: v0.3.5 Global Registry 设计（registry.json、project_key、project-scoped routing）

---

## 0. 文档定位

本文档定义 v0.4 的核心主题：将 micro-eval 从本地单机工具升级为可信内网多成员共享
Server。这是对 CLAUDE.md"不做多团队协作"边界的**主动扩围**——在保留"不做
RBAC/SSO/复杂审计"的前提下，放开"多成员读写共享"。

**本文档不是 Unicorn 的替代**。它是 Unicorn Module Map（§3）的一次**横切扩展**——在
现有 8 个模块之上引入 Server Layer（归属/队列/模板），不改变模块间契约。
ExecutionKernel、Agent Adapter、Environment/Reproducibility、Artifact/Trace、
Evaluation、Decision 各模块的接口不变；变化集中在 Configuration Layer（模板库）和
Execution Kernel 的**调度入口**（从 CLI 直接调用改为 worker 从队列取 job 调用）。

**设计前提**（已与用户澄清确认）：

| 维度 | 决策 |
|------|------|
| 部署 | 共享 server，团队成员通过浏览器访问 |
| 信任 | 可信内网，无 auth/RBAC；只需归属记录（workspace → 成员） |
| 项目模型 | 成员可建多个 workspace；一个 workspace 内多个 run |
| 执行 | run 串行——成员从浏览器发起即入队，server 一个队列顺序执行 |
| 资产 | 只读模板库（agent config / task / template），成员复制到自己 workspace 后再用再改 |
| 隔离 | run 产物按 workspace 隔离存放 |

---

## 1. Problem Statement

### 1.1 当前状态

micro-eval v0.3.x 是本地优先工具：

1. `micro-eval run` 在本地 cwd 执行，结果写入 `<cwd>/.micro-eval/runs/`。
2. `micro-eval ui` 包装 `next dev`（`main.py:31-50`），UI 通过
   `getProjectRoot()`（`api.ts:5-14`）读取单一 project root。
3. v0.3.5 的 Global Registry（`~/.micro-eval/registry.json`）解决了单机多项目汇总，
   但显式排除了远程/多机 registry 同步和多用户访问控制。
4. 执行引擎 `ExecutionKernel.run(plan)` 是纯 async 入口（`kernel.py:36-86`），
   接受 `RunPlan` + `project_root`，不依赖 CLI/tty——但只被 CLI 直接调用。

### 1.2 交付受阻

产品已过 MVP 阶段（v0.3.5，455 pytest + 42 vitest 测试），但交付对象——1-20 人 AI
小团队——无法汇集团队力量使用它：

- 成员各自在自己机器上跑 `micro-eval run`，结果散落各机，无法汇总对比。
- 没有共享的评测配置模板，团队成员重复造 eval.yaml。
- 没有从浏览器发起 run 的能力，必须 ssh 到机器手动操作。
- 没有 workspace 隔离，成员间的 run 产物会互相干扰。

### 1.3 Design Goals

1. 团队成员通过浏览器访问共享 server，查看所有 workspace 的 run 结果、发起新 run、
   写 annotation。
2. 共享只读模板库，成员从模板创建 workspace 后可自由修改自己的配置。
3. **run 级别串行**，通过队列保证——同一时刻只有一个 run 在执行。run 内部的
   cell 仍按现有 `max_concurrency` 并发执行（复用 ExecutionKernel 现有调度语义，
   不做改动）。"串行"指的是 run 之间不并发，不是 cell 之间不并发。
4. workspace 隔离——每个 workspace 有独立的 `.micro-eval/`，run 产物互不串扰。
5. 归属记录——每个 workspace、每个 run 都有 owner 标识，支持溯源。
6. 最大化复用现有执行层（ExecutionKernel、ProviderRegistry、GitWorktreeProvider、
   RunStore、SameStartSnapshot）——核心执行路径不变，仅做受控扩展：
   - `ExecutionKernel.__init__` 新增可选 `on_cell_complete` callback。
   - `RunRecord` 新增可选 `owner` 和 `server_context` 字段。
   - 新增 `build-plan` CLI 子命令（`build_run_plan()` 的薄包装）。
   - `ui/src/lib/schema.ts` 新增 `WorkspaceSchema`、`JobSchema` 等。
7. 向后兼容——`micro-eval ui` 本地单机模式保留；`micro-eval serve` 新增 server 模式。
8. 安全边界与 `security-service-guidelines.md` 对齐：server 模式下增加的攻击面
   （网络可达、多成员写入）必须有对应的防护。

### 1.4 Non-Goals

- Authentication / Authorization / RBAC / SSO（可信内网假设）。
- 多 server 集群 / 分布式队列 / 高可用。
- 跨 server 的 registry 同步。
- 并行 run 执行（串行是设计选择，不是技术限制）。
- 从浏览器编辑模板库（模板库只读，运维通过 CLI 管理）。
- 远程 agent 执行（agent 在 server 本地执行，复用现有 provider registry）。

---

## 2. Architecture Overview

### 2.1 进程模型：Next.js Server + Python Run Worker

```
┌─────────────────────────────────────────────────────────────────┐
│  共享 server 机器（可信内网）                                      │
│                                                                 │
│  ┌──────────────────┐  HTTP/JSON   ┌──────────────────────────┐ │
│  │ Next.js Server   │◄────────────►│ 团队成员浏览器              │ │
│  │ (next start)     │              │ (查看结果/发起run/annotation)│ │
│  │                  │              └──────────────────────────┘ │
│  │ API Routes:      │                                          │
│  │  GET  /api/...   │──读 workspace 数据──►┐                    │
│  │  POST /api/.../  │                      │                    │
│  │   enqueue        │──写 job──►┐          │                    │
│  │  POST /api/.../  │           │          │                    │
│  │   evaluate       │──subprocess──►Python │                    │
│  └──────────────────┘           │          │                    │
│                                 ▼          ▼                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ~/.micro-eval-server/                                   │   │
│  │    server.json          (server 配置)                     │   │
│  │    queue.db             (SQLite 任务队列)                  │   │
│  │    templates/           (只读模板库)                       │   │
│  │    workspaces/          (成员 workspace 目录)              │   │
│  │      <ws-id>/                                            │   │
│  │        workspace.json   (归属元数据)                       │   │
│  │        eval.yaml        (从模板复制的配置)                  │   │
│  │        .micro-eval/     (现有结构，平移)                    │   │
│  │          runs/<run-id>/ (run.json, decision.json, etc.)  │   │
│  │          workspaces/    (git worktree 隔离区)              │   │
│  │          index.db       (趋势 SQLite)                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                 ▲                               │
│  ┌──────────────────┐           │                               │
│  │ Run Worker       │───取 job──┘                               │
│  │ (Python 常驻)     │                                          │
│  │                  │  串行执行：                                 │
│  │  while True:     │    1. 取一条 queued job                    │
│  │    job = dequeue │    2. status = running                    │
│  │    kernel.run()  │    3. ExecutionKernel.run(plan)           │
│  │    finalize()    │    4. status = done/failed                │
│  └──────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
```

**两个进程，职责分明：**

1. **Next.js Server 进程**（Node.js）：
   - 响应浏览器 HTTP 请求。
   - 读 workspace 数据（run 结果/trace/artifact/annotation）。
   - 写 annotation（复用现有 `apply-evaluation` subprocess 模式）。
   - 把发起 run 的请求写入队列（不阻塞，立即返回 job_id）。
   - 提供 job 状态轮询接口（浏览器定时查询 run 进度）。
   - 管理 workspace（创建/列表/删除）。

2. **Run Worker 进程**（Python 常驻守护进程）：
   - 单线程循环从 SQLite 队列取 job。
   - 串行调用 `ExecutionKernel.run(plan)`——`project_root` 指向目标 workspace 目录。
   - run.json 是天然的进度/结果持久化——worker 写它，server 读它。
   - 执行完毕后更新 job 状态。

### 2.2 为什么是两个进程

- run 可能跑几十分钟，不能阻塞在 HTTP 请求里。
- 串行保证只需要 worker 单线程取 job，不需要分布式锁或 Celery/Redis。
- Next.js（Node.js）和执行引擎（Python）本来就是两个运行时。v0.3.4 的 evaluate
  subprocess 已验证跨进程协作可行（`route.ts:35-48` → `uv run micro-eval
  apply-evaluation`）。
- worker 崩溃不影响 UI 可用性（成员仍能查看历史结果）；UI 崩溃不影响正在执行的 run
  （worker 独立运行）。

### 2.3 与 Unicorn Module Map 的关系

Server Layer 不新增顶层架构模块，而是横切现有模块：

| Unicorn Module | Server 影响 |
|----------------|-------------|
| Asset Layer | 新增模板库（只读资产 registry），workspace 内的资产副本由成员自由修改 |
| Configuration Layer | RunPlan 构造从 CLI 直接调用移到 worker 内调用，接口不变 |
| Execution Kernel | 调度入口从 CLI → `asyncio.run(kernel.run(plan))` 改为 worker → `await kernel.run(plan)`，接口不变 |
| Agent Adapter | 不变（adapter 不感知 server/CLI 区别） |
| Environment/Reproducibility | `project_root` 指向 workspace 目录，worktree 自动落点——不变 |
| Artifact/Trace | `.micro-eval/` 在 workspace 内，路径自动正确——不变 |
| Evaluation | annotation 写入通过现有 subprocess 模式，cwd 指向 workspace——不变 |
| Decision | ResultMatrix / DecisionReport 在 workspace 内，UI 读取时按 workspace 路由——不变 |

**新增概念**（不属于 Unicorn 8 模块，是 Server Layer 自身）：

| 概念 | 归属 |
|------|------|
| Workspace（归属/元数据/隔离） | Server Layer |
| RunQueue（串行队列/job 状态） | Server Layer |
| TemplateRegistry（只读模板库） | Server Layer → Asset Layer 的 server-mode 扩展 |
| MemberIdentity（轻量归属标识） | Server Layer |

---

## 3. Server Data Root

### 3.1 Location

```
~/.micro-eval-server/
```

与 v0.3.5 的 `~/.micro-eval/`（registry）分离，避免单机模式和 server 模式互相干扰。
目录在 `micro-eval serve` 首次启动时创建。

### 3.2 Permissions

- `~/.micro-eval-server/` directory: mode `0o700`（owner-only）。
- 所有内部文件默认 `0o600`。
- server 进程以同一系统用户运行（可信内网假设——不做多用户系统级隔离）。

### 3.3 server.json

Server 全局配置：

```json
{
  "schema_version": "1.0",
  "server_name": "team-eval-server",
  "bind_host": "0.0.0.0",
  "bind_port": 3000,
  "data_root": "~/.micro-eval-server",
  "max_queue_size": 100,
  "run_timeout_seconds": 3600,
  "worker_poll_interval_seconds": 2,
  "allowed_hosts": []
}
```

`allowed_hosts`：Host header allowlist，用于防止 DNS rebinding（§14.6）。空数组
表示使用自动生成的默认值（`["localhost:<port>", "127.0.0.1:<port>",
"<hostname>:<port>"]`）。显式配置时可加入团队内网 DNS 名
（如 `["eval.internal:3000"]`）。

`bind_host: "0.0.0.0"` 使 server 在内网可达（默认 `next dev` 绑定 localhost）。
`run_timeout_seconds` 是单个 run 的最大执行时间（1 小时），超时后 worker 标记 job
为 failed。

---

## 4. Workspace

### 4.1 概念

Workspace 是 server 上的隔离评测环境。每个 workspace：

- 有唯一 ID（`ws-<timestamp>-<random>`）。
- 归属一个成员（owner）。
- 包含自己的 eval.yaml（从模板复制而来，可自由修改）。
- 有独立的 `.micro-eval/`（run 产物、git worktree 隔离区、趋势索引）。
- 逻辑上等同于现有 `project_root`——所有现有代码以 workspace 目录作为
  `project_root` 即可工作。

### 4.2 Physical Layout

```
~/.micro-eval-server/workspaces/<workspace-id>/
  workspace.json              # 归属元数据
  eval.yaml                   # 从模板复制来的配置（成员可改）
  tasks/                      # 从模板复制来的任务定义（成员可改）
  .micro-eval/
    runs/<run-id>/            # 现有结构，平移
      run.json
      decision.json
      cells/
      artifacts/
      traces/
    workspaces/<run-id>/      # git worktree 隔离区（GitWorktreeProvider）
    index.db                  # SQLite 趋势索引
```

### 4.3 workspace.json Schema

```json
{
  "schema_version": "1.0",
  "workspace_id": "ws-20260619T091803Z-a3f7b2c1",
  "name": "agent-codefix-evaluation",
  "owner": "alice",
  "template_id": "agent-showdown-v2",
  "template_version": "1.0.0",
  "created_at": "2026-06-19T09:18:03Z",
  "last_run_at": "2026-06-19T10:30:00Z",
  "run_count": 5,
  "description": "Testing Claude vs GPT on codefix tasks",
  "git_pin": {
    "repo": "https://github.com/team/eval-fixtures.git",
    "commit": "abc1234",
    "branch": "main"
  },
  "status": "active"
}
```

**字段说明**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `workspace_id` | 是 | 格式 `ws-<ISO8601Compact>-<8hexrand>`，全局唯一 |
| `name` | 是 | 人类可读名称，显示用 |
| `owner` | 是 | 成员标识（§5 MemberIdentity） |
| `template_id` | 否 | 来源模板 ID（若从模板创建） |
| `template_version` | 否 | 来源模板版本（创建时快照，不随模板更新） |
| `created_at` | 是 | ISO 8601 UTC |
| `last_run_at` | 否 | 最近一次 run 完成时间 |
| `run_count` | 是 | hint，真实值由 runs 目录扫描得出 |
| `description` | 否 | 自由文本 |
| `git_pin` | 否 | 如果 workspace 关联外部 fixture repo |
| `status` | 是 | `active` \| `archived` |

### 4.4 Workspace Lifecycle

```
创建 workspace（从模板或空白）
    │
    ▼
active ──── 成员修改 eval.yaml / 发起 run / 写 annotation
    │
    ▼  (成员手动归档)
archived ── UI 不在默认列表显示，run 数据保留
    │
    ▼  (成员手动删除)
deleted ─── 整个 workspace 目录删除（不可恢复）
```

### 4.5 Workspace Operations

| 操作 | 入口 | 行为 |
|------|------|------|
| 创建（从模板） | API `POST /api/workspaces` + CLI `micro-eval workspace create` | 复制模板到新目录，生成 workspace.json |
| 创建（空白） | 同上，不指定 template_id | 创建空目录 + workspace.json + 空 eval.yaml |
| 列表 | API `GET /api/workspaces` + CLI `micro-eval workspace list` | 列出所有 active workspace |
| 查看 | API `GET /api/workspaces/[id]` | 返回 workspace 元数据 + run 统计 |
| 更新元数据 | API `PATCH /api/workspaces/[id]` | 修改 name/description/status |
| 归档 | API `PATCH /api/workspaces/[id]` status=archived | 从默认列表隐藏 |
| 删除 | API `DELETE /api/workspaces/[id]` + CLI `micro-eval workspace delete` | 删除整个目录 |

### 4.5.1 Workspace-Queue 互锁规则

Workspace 生命周期操作必须与队列状态联动，避免状态歧义：

| 操作 | 有 queued/running job 时 | 理由 |
|------|--------------------------|------|
| 归档 | **拒绝**（409 Conflict） | 防止归档后 worker 仍在写入产物 |
| 删除 | **拒绝**（409 Conflict） | 防止删除正在使用的目录 |
| 编辑 eval.yaml | **允许** | 不影响已入队 job（job 使用入队时冻结的 `plan_json`） |
| 发起新 run（enqueue） | **允许**（仅 active workspace） | 新 job 排入队列末尾 |

**关键不变式**：已入队的 job 使用入队时冻结的 `plan_json`，后续对 eval.yaml 的
编辑不影响已入队 job 的执行。UI 在归档/删除操作时，如果有 pending job，应显示
明确提示（"该 workspace 有 N 个待执行/执行中的 job，请先取消或等待完成"）。

### 4.6 Workspace Path Validation

所有通过 API 访问 workspace 的路径必须经过验证：

```typescript
function resolveWorkspacePath(workspaceId: string): string | null {
  // workspace_id must match format: ws-<timestamp>-<hex>
  if (!/^ws-[0-9T]{15,}Z-[a-f0-9]{8}$/.test(workspaceId)) return null;

  const dataRoot = getServerDataRoot();
  const wsDir = path.resolve(dataRoot, "workspaces", workspaceId);

  // Containment check: workspace must be inside data root
  if (!wsDir.startsWith(path.resolve(dataRoot, "workspaces") + path.sep)) return null;

  // Resolve symlinks and re-check
  try {
    const realWsDir = fs.realpathSync(wsDir);
    const realWsRoot = fs.realpathSync(path.resolve(dataRoot, "workspaces"));
    if (!realWsDir.startsWith(realWsRoot + path.sep)) return null;
    return realWsDir;
  } catch {
    return null;
  }
}
```

这延续了 v0.3.5 Global Registry 的 path validation 模式（§7.3），但验证对象从
registry 的 project path 变为 workspace path。

---

## 5. Member Identity

### 5.1 设计原则

可信内网——不做 auth。成员身份是**归属标识**，不是访问控制。

### 5.2 Identity Model

成员通过 HTTP header 自报身份：

```
X-Micro-Eval-Member: alice
```

- 无验证（可信内网假设）。
- **读接口**（GET）：header 缺失时使用 `anonymous`（读操作不做身份限制）。
- **写接口**（POST/PUT/PATCH/DELETE）：header **必须存在**且符合成员名规则
  （§5.3），否则返回 `400 Bad Request`。这既保证归属记录完整性，也作为
  CSRF 防护的一部分（§14.6）。
- 成员名只用于归属记录（workspace.owner、job.owner、run.json 内的 owner 字段），
  不用于权限判断。

### 5.3 成员名规则

- 1-64 字符，`[a-zA-Z0-9._-]`。
- 大小写敏感（`alice` 和 `Alice` 是不同成员）。
- 不做唯一性校验或注册——首次出现即创建。

### 5.4 归属记录

归属记录写入以下位置：

| 记录位置 | 字段 | 写入时机 |
|----------|------|----------|
| `workspace.json` | `owner` | workspace 创建时 |
| `queue.db` jobs 表 | `owner` | run 入队时 |
| `run.json` | `owner` | run 开始执行时（worker 从 job 复制 owner 到 RunRecord） |
| annotation evidence | `evaluator` | 成员写 annotation 时（现有 `evaluator` 字段） |

### 5.5 Server API 的身份感知

- **写操作**：`X-Micro-Eval-Member` header 必须存在且合法（§5.2），否则返回
  `400 Bad Request`。归属记录写入对应位置。
- **读操作**：header 可选，缺失时视为 `anonymous`。不做权限过滤——任何成员可以
  看到所有 workspace 的所有 run（可信内网假设，透明度是团队协作的基础）。

### 5.6 未来演进

如果需要从可信内网迁移到需要 auth 的场景，`X-Micro-Eval-Member` 可以被替换为
token-based auth，归属记录的数据模型不变。这一步在 Non-Goals 中，此设计不为其
预留复杂接口。

---

## 6. Template Registry

### 6.1 概念

模板库是 server 上的只读资产 registry。成员创建 workspace 时从模板复制一份配置到
自己的 workspace，之后独立修改。

### 6.2 Physical Layout

```
~/.micro-eval-server/templates/
  <template-id>/
    template.json             # 模板元数据
    eval.yaml                 # 模板配置（agent config / task 引用 / workspace spec）
    tasks/                    # 任务定义文件
      task-a.yaml
      task-b.yaml
    fixtures/                 # 可选：fixture 文件
```

### 6.3 template.json Schema

```json
{
  "schema_version": "1.0",
  "template_id": "agent-showdown-v2",
  "name": "Agent Codefix Showdown",
  "description": "Compare coding agents on real-world bug fixes",
  "version": "1.0.0",
  "created_at": "2026-06-19T09:00:00Z",
  "updated_at": "2026-06-19T09:00:00Z",
  "author": "admin",
  "tags": ["codefix", "agent-comparison"],
  "includes": {
    "eval_yaml": true,
    "tasks": ["task-a.yaml", "task-b.yaml"],
    "fixtures": ["fixture-repo.tar.gz"]
  }
}
```

### 6.4 Template Lifecycle

模板库是**版本化可更新**的只读资产库（只读指的是浏览器 API 不提供写入接口，
运维通过 CLI 管理）：

- **创建**：运维通过 `micro-eval template create <dir>` 从本地目录打包成模板。
- **更新**：运维通过 `micro-eval template update <id> <dir>` 更新模板内容，
  version 字段递增。已创建的 workspace 不受影响（创建时快照了 template_version）。
- **列表**：`micro-eval template list` 或 API `GET /api/templates`。
- **删除**：`micro-eval template delete <id>`。不删除已从此模板创建的 workspace。

### 6.5 只读保证

Next.js Server 和 Run Worker 都只读取模板目录，不写入。写入操作只通过
`micro-eval template` CLI（需要 server 机器的 shell 访问权限）。浏览器 API 不提供
模板写入接口。

### 6.6 从模板创建 Workspace

```
POST /api/workspaces
{
  "name": "my-codefix-eval",
  "template_id": "agent-showdown-v2",
  "owner": "alice"  // 从 X-Micro-Eval-Member header 自动填入
}
```

Server 执行：

1. 验证 template_id 存在。
2. 生成 workspace_id。
3. 创建 workspace 目录。
4. `cp -r` 模板目录内容到 workspace（eval.yaml + tasks/ + fixtures/）。
5. 写 workspace.json（记录 template_id、template_version、owner）。
6. 返回 workspace 元数据。

---

## 7. Run Queue

### 7.1 Storage

SQLite 数据库 `~/.micro-eval-server/queue.db`，一张 jobs 表：

```sql
CREATE TABLE IF NOT EXISTS jobs (
  job_id       TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  owner        TEXT NOT NULL,
  plan_json    TEXT NOT NULL,  -- serialized RunPlan
  status       TEXT NOT NULL DEFAULT 'queued',
    -- queued | running | done | failed | cancelled
  enqueued_at  TEXT NOT NULL,  -- ISO 8601 UTC
  started_at   TEXT,
  finished_at  TEXT,
  run_id       TEXT,           -- set when worker picks up job (from RunPlan.run_id)
  error        TEXT,           -- set on failure
  progress          TEXT,      -- optional JSON: {completed_cells, total_cells, ...}
  cancel_requested_at TEXT,    -- ISO 8601 UTC, set when cancel is requested
  cancelled_by       TEXT      -- member who cancelled (from X-Micro-Eval-Member)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_workspace ON jobs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_jobs_enqueued ON jobs(enqueued_at);
```

### 7.2 为什么用 SQLite

- 单 server 部署——不需要外部服务（Redis/RabbitMQ）。
- SQLite WAL 模式支持 reader-writer 并发——Next.js 读、worker 写不互阻。
- 项目已使用 SQLite 做趋势索引（`index.db`），技术栈一致。
- 队列容量极小（100 条上限），SQLite 足够。
- 崩溃恢复简单——SQLite ACID 保证。

**WAL 模式必须显式启用**：`QueueDB.__init__` 在打开连接后执行
`PRAGMA journal_mode=WAL`，确保 reader-writer 并发生效。

### 7.3 Job Lifecycle

```
enqueue (浏览器 POST)
    │
    ▼
queued ─────── 等待 worker 取走
    │
    ▼  (worker 取走)
running ────── ExecutionKernel.run(plan) 执行中
    │          worker 定期更新 progress
    │
    ├─────▶ done ────── 执行成功，run.json 已写入 workspace
    │
    ├─────▶ failed ──── 执行失败，error 字段记录原因
    │
    └─────▶ cancelled ─ 用户取消（§7.8）
```

### 7.4 Enqueue（浏览器发起 run）

```
POST /api/workspaces/[id]/runs/enqueue
{
  "config_overrides": {}  // optional: 覆盖 eval.yaml 中的部分配置
}

Response 201:
{
  "job_id": "job-20260619T103000Z-b2c3d4e5",
  "status": "queued",
  "position": 3  // 在队列中的位置
}
```

Server 执行：

1. 验证 workspace_id 存在且 status=active。
2. 读 workspace 的 eval.yaml，构造 RunPlan（调用 Python subprocess：
   `uv run micro-eval build-plan --workspace <path> [--overrides <json>]`）。
3. 将 job 写入 queue.db。
4. 返回 job_id 和队列位置。

**新增 CLI 子命令 `micro-eval build-plan`**：从 eval.yaml 构造 RunPlan 并输出
JSON 到 stdout。这是 `run.py` 中 `build_run_plan()` + `load_config()` 的薄包装，
分离 plan 构造与 plan 执行，供 server enqueue 流程使用。

### 7.5 Worker 执行循环

```python
async def worker_loop(data_root: Path, poll_interval: float = 2.0):
    db = QueueDB(data_root / "queue.db")
    while True:
        job = db.dequeue_next()  # SELECT ... WHERE status='queued' ORDER BY enqueued_at LIMIT 1
        if job is None:
            await asyncio.sleep(poll_interval)
            continue

        ws_path = data_root / "workspaces" / job.workspace_id
        try:
            plan = RunPlan.from_json(job.plan_json)
            run_id = plan.run_id  # run_id is determined at plan construction time
            db.update_status(job.job_id, "running", started_at=utcnow(), run_id=run_id)

            kernel = ExecutionKernel(project_root=ws_path)
            # Timeout enforced via asyncio.wait_for
            record = await asyncio.wait_for(
                kernel.run(plan),
                timeout=config.run_timeout_seconds,
            )
            # finalize_run already writes run.json and indexes to SQLite
            # Check if cancellation was requested during execution
            if db.is_cancel_requested(job.job_id):
                db.update_status(job.job_id, "cancelled", finished_at=utcnow())
            else:
                db.update_status(job.job_id, "done", finished_at=utcnow())
        except asyncio.TimeoutError:
            db.update_status(
                job.job_id, "failed", finished_at=utcnow(),
                error=f"run timed out after {config.run_timeout_seconds}s",
            )
        except Exception as e:
            db.update_status(job.job_id, "failed", finished_at=utcnow(), error=str(e))
```

**关键点**：

- `ExecutionKernel(project_root=ws_path)` 就是全部——workspace 目录作为 project_root，
  worktree 隔离、run.json 写入、provider registry 全部自动落在 workspace 下。
- worker 是单线程 asyncio 循环——串行保证来自"一次只取一个 job"。
- `dequeue_next()` 使用 SQLite 事务：`UPDATE jobs SET status='running' WHERE
  job_id = (SELECT job_id FROM jobs WHERE status='queued' ORDER BY enqueued_at
  LIMIT 1) RETURNING *`——atomic dequeue，不需要额外锁。
- **超时语义**：`asyncio.wait_for` 在超时时取消 `kernel.run()` 的 asyncio Task。
  `asyncio.CancelledError` 会传播到正在 `await` 的 agent subprocess，但不会
  强杀已 spawn 的子进程——provider 的 `subprocess.Popen` 进程可能仍在运行。
  v0.4 不保证强杀所有下游 provider 进程（需要 provider-level cleanup 协议，超出
  本版范围）。run.json 中已完成的 cell 结果会被保留（`finalize_run` 在正常
  退出路径中调用；超时路径下部分结果可能丢失——这是已知限制）。

### 7.6 Job Status Polling

浏览器定期轮询 job 状态：

```
GET /api/jobs/[jobId]

Response 200:
{
  "job_id": "job-20260619T103000Z-b2c3d4e5",
  "workspace_id": "ws-20260619T091803Z-a3f7b2c1",
  "owner": "alice",
  "status": "running",
  "enqueued_at": "2026-06-19T10:30:00Z",
  "started_at": "2026-06-19T10:30:05Z",
  "progress": {
    "current_cell": 3,
    "total_cells": 12,
    "current_task": "task-fix-auth-bug",
    "current_config": "claude-sonnet-4-6"
  }
}
```

轮询间隔建议 5 秒。当 status 变为 done/failed/cancelled 时，UI 跳转到 run 详情页
或显示错误。

### 7.7 Queue Dashboard

```
GET /api/queue

Response 200:
{
  "running": { "job_id": "...", "workspace_id": "...", "owner": "alice", ... },
  "queued": [
    { "job_id": "...", "workspace_id": "...", "owner": "bob", "position": 1, ... },
    { "job_id": "...", "workspace_id": "...", "owner": "charlie", "position": 2, ... }
  ],
  "recent_completed": [
    { "job_id": "...", "status": "done", "run_id": "run-...", ... }
  ]
}
```

UI 在 landing page 显示当前队列状态：谁在跑、谁在排队、最近完成的 run。

### 7.8 Job Cancellation

```
POST /api/jobs/[jobId]/cancel

# queued job → 立即取消
Response 200:
{ "job_id": "...", "status": "cancelled", "cancel_requested_at": "2026-..." }

# running job → 仅标记取消请求，状态仍为 running
Response 200:
{ "job_id": "...", "status": "running", "cancel_requested_at": "2026-..." }

# done/failed/cancelled → 已终止
Response 409:
{ "error": "job_already_terminated", "status": "done" }
```

- **queued → cancelled**：直接将 job status 更新为 `cancelled`，设置
  `cancelled_by`、`cancel_requested_at` 和 `finished_at`。立即生效。
- **running（stop-after-run）**：将 job 的 `cancel_requested_at` 字段设为当前时间，
  `cancelled_by` 设为请求者身份。**job status 仍为 `running`**——API 响应返回
  当前真实状态 `running` 加上 `cancel_requested_at` 字段，不返回 `cancelled`。
  当前 run 继续执行到完成——不中断正在执行的 cell，不修改 ExecutionKernel 调度逻辑。
  run 正常完成后，worker 检查 `cancel_requested_at` 是否非空：如果是，将 job 标记
  为 `cancelled`（而非 `done`），run.json 仍保留已完成的结果。
  - **设计选择**：v0.4 不在 cell 级别拦截取消（这需要修改 ExecutionKernel 的 asyncio
    task dispatch 逻辑，复杂度高且收益有限——一个 run 通常几分钟到一小时）。
    "stop-after-run" 语义简单、可测试、不侵入现有内核。
  - UI 在 running job 上检测 `cancel_requested_at` 非空时显示
    "已请求取消，等待当前 run 完成"状态。
- **done/failed/cancelled → cancel**：返回 `409 Conflict`，已终止的 job 不可再取消。
- 任何成员可以取消任何 job（可信内网假设——不做权限检查）。`cancelled_by` 字段
  记录请求者身份以支持溯源。

**`GET /api/jobs/[jobId]` 响应**始终包含 `cancel_requested_at` 字段（null 或
ISO 8601 时间戳），前端据此判断是否显示取消请求状态。

### 7.9 Run Progress Reporting

Worker 在执行过程中定期更新 progress：

```python
# In ExecutionKernel.run(), after each cell completes:
db.update_progress(job.job_id, {
    "current_cell": cell_index + 1,
    "total_cells": total_cells,
    "current_task": cell.task_id,
    "current_config": cell.configuration_id,
})
```

这要求 ExecutionKernel 接受一个可选的 progress callback。现有
`kernel.run()` 内部使用 asyncio 并发执行 cell（按 `max_concurrency`）——在每个
cell 完成后调用 callback 是非侵入式改动。callback 接收完成计数（原子递增），
不依赖执行顺序：

```python
class ExecutionKernel:
    def __init__(self, project_root: Path, on_cell_complete: Callable | None = None):
        ...
        self._on_cell_complete = on_cell_complete

    async def run(self, plan: RunPlan) -> RunRecord:
        ...
        completed = 0
        async def run_cell(cell):
            nonlocal completed
            result = await self._execute_cell(cell)
            completed += 1
            if self._on_cell_complete:
                self._on_cell_complete(completed, len(cells), cell)
            return result
        # cells are dispatched via asyncio with max_concurrency
        ...
```

### 7.10 Queue Overflow

当队列达到 `max_queue_size`（默认 100），新的 enqueue 请求返回 `429 Too Many
Requests`：

```json
{
  "error": "queue_full",
  "message": "Run queue is full (100/100). Please wait for running jobs to complete.",
  "queue_size": 100
}
```

### 7.11 Crash Recovery

Worker 启动时扫描 queue.db，找到所有 status=running 的 job（此时 `run_id` 已在
job 开始执行时写入，见 §7.5）：

- 用 `workspace_id + run_id` 定位 `run.json`。
- 如果 `run.json` 存在且有 `completed_at`：
  - 如果 `cancel_requested_at IS NOT NULL`——说明 run 完成但取消请求在 crash 前
    已记录。标记 job 为 `cancelled`。
  - 否则——说明 run 正常完成但 worker 在更新 job 状态前崩溃。标记 job 为 `done`。
- 如果 `run.json` 不存在或没有 `completed_at`——说明 run 被中断。标记 job 为
  `failed`，error 记录 `"worker crashed during execution"`。

---

## 8. Server Launch

### 8.1 `micro-eval serve` 命令

```bash
micro-eval serve [--port 3000] [--host 0.0.0.0] [--data-root ~/.micro-eval-server]
```

执行流程：

1. 确保 `data_root` 目录存在（不存在则创建，mode `0o700`）。
2. 初始化 `server.json`（如果不存在，写入默认配置）。
3. 初始化 `queue.db`（如果不存在，创建表）。
4. 启动 Run Worker 作为子进程（`uv run micro-eval worker --data-root <path>`）。
5. 启动 Next.js Server（`next start --port <port> --hostname <host>`）。
   - 环境变量 `MICRO_EVAL_SERVER_MODE=true` 和 `MICRO_EVAL_DATA_ROOT=<path>`
     传递给 Next.js，使 UI 数据层切换到 server 模式。
6. 捕获 SIGINT/SIGTERM，先停 worker 再停 server。

### 8.2 `micro-eval worker` 命令

```bash
micro-eval worker --data-root ~/.micro-eval-server
```

独立的 Python 常驻守护进程。`serve` 自动启动它，也可以手动启动（方便调试）。

**Worker 重复启动防护**：worker 启动时在 `data_root` 下写 PID 文件
（`worker.pid`）。如果 PID 文件已存在且进程仍在运行，worker 拒绝启动并报错
`"Another worker is already running (PID: ...)"`)。进程退出时（包括 crash）由
`serve` 命令负责清理 PID 文件。手动启动 worker 时，worker 自身在 `atexit` 中
清理 PID 文件。

### 8.3 `micro-eval ui` 保持不变

`micro-eval ui` 仍然是本地单机模式——起 `next dev`，读本地 `.micro-eval/`。
不受 server 模式影响。两种模式互不干扰。

### 8.4 Next.js Build

Server 模式用 `next start`（production build），不是 `next dev`。`micro-eval
serve` 在首次运行时需要 `next build`——或者在安装/部署时预构建。

`micro-eval serve` 启动时检查 `ui/.next/` 是否存在：
- 存在 → 直接 `next start`。
- 不存在 → 先执行 `npm run build`（`cwd=ui/`），然后 `next start`。

**Build 失败处理**：如果 `npm run build` 以非零退出，`serve` 命令应：
1. 输出 build 错误日志到 stderr。
2. 停止已启动的 worker 子进程。
3. 以非零退出码退出（不尝试启动 `next start`）。

---

## 9. UI Data Layer Changes

### 9.1 Mode Detection

```typescript
// ui/src/lib/server-mode.ts
export function isServerMode(): boolean {
  return process.env.MICRO_EVAL_SERVER_MODE === "true";
}

export function getServerDataRoot(): string {
  return process.env.MICRO_EVAL_DATA_ROOT || path.join(os.homedir(), ".micro-eval-server");
}
```

### 9.2 Data Layer Routing

现有 `api.ts` 的函数（`getProjectRoot`、`getRunsDir`、`listRuns`、`getRun` 等）
在 server 模式下按 workspace 路由：

```typescript
// Server mode: workspace-scoped
function getWorkspaceRunsDir(workspaceId: string): string | null {
  const wsPath = resolveWorkspacePath(workspaceId);
  if (!wsPath) return null;
  return path.join(wsPath, ".micro-eval", "runs");
}

// Legacy mode: single project root (unchanged)
function getLegacyRunsDir(): string {
  return path.join(getProjectRoot(), ".micro-eval", "runs");
}
```

现有 `getRunFromDir(runsDir, id)` 模式（v0.3.5 Global Registry 引入的参数化内部
helper）直接复用——只是 `runsDir` 的来源从 registry lookup 变成 workspace lookup。

### 9.3 与 v0.3.5 Global Registry 的关系

Server 模式下，v0.3.5 的 `~/.micro-eval/registry.json` **不使用**。Server 有自己
的 workspace registry（`~/.micro-eval-server/workspaces/` 目录 + 各 workspace.json）。

如果同一台机器同时用于本地开发（`micro-eval ui`）和 server（`micro-eval serve`），
两套数据完全独立，互不感知。

### 9.4 Evaluate Subprocess

现有 evaluate subprocess 模式（`route.ts:35-48` → `uv run micro-eval
apply-evaluation --run-id ... --cell-id ...`）在 server 模式下，`cwd` 从
`getProjectRoot()` 改为 `resolveWorkspacePath(workspaceId)`：

```typescript
// Server mode evaluate
const wsPath = resolveWorkspacePath(workspaceId);
if (!wsPath) return NextResponse.json({ error: "workspace not found" }, { status: 404 });

const stdout = execFileSync(uvBin, args, {
  input: JSON.stringify(input),
  encoding: "utf-8",
  cwd: wsPath,  // workspace root as cwd
  timeout: 30_000,
});
```

Python 侧 `evaluate.py:24` 的 `project_root = Path.cwd()` 自然指向 workspace，
无需修改 Python 代码。

---

## 10. API Routes

### 10.1 Server Mode Routes

Server 模式下的 API routes（与 v0.3.5 project-scoped routes 并列，不替换）：

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/server/status` | Server 状态（uptime、worker 状态、队列统计） |
| `GET` | `/api/templates` | 列出所有模板 |
| `GET` | `/api/templates/[id]` | 模板详情 |
| `GET` | `/api/workspaces` | 列出所有 active workspace |
| `POST` | `/api/workspaces` | 创建 workspace（从模板或空白） |
| `GET` | `/api/workspaces/[id]` | Workspace 元数据 + run 统计 |
| `PATCH` | `/api/workspaces/[id]` | 更新 workspace 元数据 |
| `DELETE` | `/api/workspaces/[id]` | 删除 workspace |
| `GET` | `/api/workspaces/[id]/runs` | Workspace 内的 run 列表 |
| `GET` | `/api/workspaces/[id]/runs/[runId]` | Run 详情 |
| `GET` | `/api/workspaces/[id]/runs/[runId]/cells/[cellId]` | Cell 详情 |
| `GET` | `/api/workspaces/[id]/runs/[runId]/cells/[cellId]/trace` | Cell trace |
| `GET` | `/api/workspaces/[id]/runs/[runId]/artifacts` | Run artifacts |
| `POST` | `/api/workspaces/[id]/runs/[runId]/cells/[cellId]/evaluate` | 写 annotation |
| `GET` | `/api/workspaces/[id]/trends` | Workspace 趋势 |
| `POST` | `/api/workspaces/[id]/runs/enqueue` | 发起 run（入队） |
| `GET` | `/api/queue` | 队列 dashboard |
| `GET` | `/api/jobs/[jobId]` | Job 状态 |
| `POST` | `/api/jobs/[jobId]/cancel` | 取消 job |

### 10.2 路由前缀分离

Server 模式的 routes 使用 `/api/workspaces/` 和 `/api/server/` 前缀，与 v0.3.5
的 `/api/project/` 前缀不冲突。非 server 模式下，server routes 返回 404。

### 10.3 所有 workspace-scoped API 的通用安全检查

每个 `/api/workspaces/[id]/...` route handler 开头：

1. 调用 `resolveWorkspacePath(id)` 验证 workspace 存在且路径合法。
2. 读 `workspace.json` 确认 status ≠ deleted。
3. 对于写操作：验证 `X-Micro-Eval-Member` header 存在且符合成员名规则（§5.3），
   缺失或非法时返回 `400 Bad Request`。验证 `Content-Type: application/json`。
   验证 `Host` header 在 allowlist 中（§14.6）。记录操作者身份到归属记录。

---

## 11. UI Pages

### 11.1 Server Mode Landing Page

当 `isServerMode()` 为 true 时，`/` 显示 server dashboard 而非 project card grid：

- **队列状态卡片**：当前 running job（谁在跑什么）、queued jobs 数量、最近完成。
- **Workspace 列表**：卡片网格，每张卡片显示 workspace name、owner、run count、
  last run、最新 verdict。排序：last_run_at 降序。
- **模板库入口**：链接到模板列表页。

### 11.2 Page Routes

| Route | Content |
|-------|---------|
| `/` | Server dashboard（server mode）或 project cards（legacy mode） |
| `/workspaces` | Workspace 列表（全量，含 archived） |
| `/workspaces/new` | 创建 workspace 表单（选模板/空白） |
| `/workspace/[id]` | Workspace 详情 + run 列表 |
| `/workspace/[id]/run/[runId]` | Run 详情（复用现有 RunDetail 组件） |
| `/workspace/[id]/run/[runId]/review` | Review 页（复用现有 ReviewPage） |
| `/workspace/[id]/run/[runId]/artifact/[artifactId]` | Artifact 查看（复用现有） |
| `/workspace/[id]/config` | 查看/编辑 workspace 的 eval.yaml（新组件） |
| `/templates` | 模板列表 |
| `/templates/[id]` | 模板详情 |
| `/queue` | 队列 dashboard（全屏版） |

### 11.3 Components

新增组件：

| Component | Description |
|-----------|-------------|
| `WorkspaceCard.tsx` | Workspace 卡片（name、owner、runs、verdict） |
| `WorkspaceList.tsx` | Workspace 卡片网格 |
| `WorkspaceCreateForm.tsx` | 创建 workspace 表单 |
| `QueueDashboard.tsx` | 队列状态面板 |
| `QueueJobCard.tsx` | 单个 job 状态卡片 |
| `RunEnqueueButton.tsx` | 发起 run 按钮（入队 + 轮询 + 跳转） |
| `ConfigEditor.tsx` | eval.yaml 查看/编辑器（server 模式） |
| `TemplateCard.tsx` | 模板卡片 |
| `TemplateList.tsx` | 模板卡片网格 |
| `MemberBadge.tsx` | 成员名徽章（显示归属） |

现有组件改动：

| Component | Change |
|-----------|--------|
| `RunList.tsx` | 接受 `workspaceId` prop（server 模式）或 `projectKey` prop（legacy） |
| `CellDetail.tsx` | 同上 |
| `MatrixHeatmap.tsx` | 同上 |
| `AnnotationPanel.tsx` | POST URL 使用 workspace-scoped endpoint |

### 11.4 eval.yaml 编辑

Server 模式下，任何成员可以通过浏览器查看和编辑**任何** workspace 的 eval.yaml
（可信内网假设——不做权限检查，与其他写操作一致）。config 编辑记录操作者身份
（来自 `X-Micro-Eval-Member` header）用于溯源：

```
GET /api/workspaces/[id]/config
→ { content: "yaml string...", last_modified: "..." }

PUT /api/workspaces/[id]/config
{ content: "yaml string..." }
→ { ok: true }
```

Server 对 config 写入做基本校验（YAML 语法、必填字段），但不做语义验证——语义错误
在 run 构造 plan 时暴露。

---

## 12. New CLI Commands

### 12.1 Server 管理

| Command | Description |
|---------|-------------|
| `micro-eval serve` | 启动 server（Next.js + worker） |
| `micro-eval worker` | 启动 worker（独立守护进程，serve 自动调用） |

### 12.2 Workspace 管理

| Command | Description |
|---------|-------------|
| `micro-eval workspace create [--name NAME] [--template ID] [--owner OWNER]` | 创建 workspace |
| `micro-eval workspace list [--all]` | 列出 workspace（默认 active，--all 含 archived） |
| `micro-eval workspace delete <workspace-id>` | 删除 workspace（交互确认） |

### 12.3 Template 管理

| Command | Description |
|---------|-------------|
| `micro-eval template create <dir> [--id ID] [--name NAME]` | 从本地目录创建模板 |
| `micro-eval template update <id> <dir>` | 更新模板 |
| `micro-eval template list` | 列出模板 |
| `micro-eval template delete <id>` | 删除模板 |

### 12.4 Plan 构造

| Command | Description |
|---------|-------------|
| `micro-eval build-plan --workspace <path> [--overrides <json>]` | 构造 RunPlan 输出 JSON |

### 12.5 Queue 管理

| Command | Description |
|---------|-------------|
| `micro-eval queue status` | 显示队列状态 |
| `micro-eval queue cancel <job-id>` | 取消 job |

---

## 13. SameStartSnapshot 在 Server 模式下的增强

### 13.1 观察

Server 串行执行意外地**强化了** SameStartSnapshot（P3 头号痛点）：

- 单机时 workspace 状态可能被开发者随手改动。
- Server 上每个 run 从一个命名的、归属明确的 workspace 起跑。串行执行意味着
  没有并发修改。
- 溯源链"谁、在哪个 workspace、从哪个 commit、用了哪个模板版本、跑了什么"
  比单机更可信。

### 13.2 Server 模式下的 Snapshot 扩展字段

RunRecord 在 server 模式下额外记录：

```json
{
  "server_context": {
    "workspace_id": "ws-20260619T091803Z-a3f7b2c1",
    "owner": "alice",
    "template_id": "agent-showdown-v2",
    "template_version": "1.0.0",
    "job_id": "job-20260619T103000Z-b2c3d4e5",
    "server_name": "team-eval-server"
  }
}
```

这些字段是**附加元数据**，不改变现有 SameStartSnapshot 的 comparability digest
计算——但它们增加了溯源链的深度，让团队对"这个结论怎么来的"有更完整的可信回溯。

---

## 14. Security Considerations

### 14.1 Attack Surface Expansion

Server 模式把 micro-eval 从"本地进程读本地文件"变成"网络可达的 HTTP server"。
即使是可信内网，也需要防护以下场景。

### 14.2 Path Traversal

所有 workspace/template/run/artifact 路径访问必须经过 containment 验证：

- Workspace ID 格式校验（`ws-<timestamp>-<hex>`）。
- 解析后的路径必须在 `data_root/workspaces/` 或 `data_root/templates/` 内。
- symlink 解析后重新检查 containment。
- 不接受 raw filesystem path 作为 API 参数——只接受 ID（workspace_id、run_id、
  artifact_id），由 server 内部解析为路径。

这与 v0.3.5 Global Registry 的 `validateProjectPath()`（§7.3）和现有
`api.ts:100-106` 的 artifact path validation 是同一模式。

### 14.3 Queue Injection

- `plan_json` 是 server 内部构造的（通过调用 `micro-eval build-plan`），不是浏览器
  直接提交的。浏览器只提交 workspace_id 和可选的 config_overrides。
- `config_overrides` 只允许覆盖白名单字段（如 repetitions、timeout），不允许覆盖
  agent command 或 workspace path。

### 14.4 Subprocess Safety

所有 subprocess 调用（`build-plan`、`apply-evaluation`、agent 执行）延续现有
安全规范：

- 安全 argv（不做 shell 字符串插值）。
- stdin/文件传参。
- env allowlist。
- secret redaction。

### 14.5 Denial of Service

- `max_queue_size` 防止队列无限增长。
- `run_timeout_seconds` 防止单个 run 无限执行。
- eval.yaml 编辑的 PUT 请求限制 body size（1MB）。
- 无 rate limiting（可信内网假设——如果团队 1-20 人，不需要 rate limit）。

### 14.6 Cross-Origin / CSRF Protection

Server 绑定 `0.0.0.0` 后，浏览器中的恶意网页可以尝试向 server 发送跨站请求
（CSRF）。即使在可信内网中，也需要防止"用户在内网浏览器中打开恶意链接后，该
链接自动向 micro-eval server 发起写操作"的场景。

**防护策略**（阻断跨源简单请求的最小防护——所有写接口必须实施）：

1. **Content-Type 强制**：所有 POST/PUT/PATCH/DELETE 接口只接受
   `Content-Type: application/json`。拒绝 `application/x-www-form-urlencoded`、
   `multipart/form-data`、`text/plain`。这阻止了浏览器 `<form>` 和
   `navigator.sendBeacon()` 的自动跨站请求（它们只能发送 simple content types）。
2. **自定义 header 检查**：所有写接口要求请求携带 `X-Micro-Eval-Member` header
   （已在 §5 中定义）。浏览器的跨站简单请求不能设置自定义 header（需要 preflight），
   而 server 不提供 CORS headers（不返回 `Access-Control-Allow-Origin`），所以
   preflight 会被浏览器拒绝。
3. **不返回 CORS headers**：server 不在任何响应中返回 `Access-Control-Allow-Origin`
   或 `Access-Control-Allow-Headers`。这意味着只有同源页面（即 micro-eval UI 自身）
   的 `fetch()` 请求能成功携带自定义 header。
4. **Host header allowlist**：server 维护一个允许的 Host 值列表（默认
   `["localhost:<port>", "127.0.0.1:<port>", "<hostname>:<port>"]`，由 `serve`
   命令根据 `bind_host` 和 `bind_port` 自动生成，也可在 `server.json` 中显式
   配置 `allowed_hosts`）。所有请求的 `Host` header 必须匹配 allowlist 中的某一
   项，否则返回 `400 Bad Request`。这防止 DNS rebinding 攻击——攻击者注册一个域名
   解析到内网 IP，浏览器认为该域名是"同源"，但 Host header 会携带攻击者的域名
   而非 allowlist 中的值，请求被拒绝。

**已知限制**：以上四层防护覆盖了跨源简单请求、跨源 preflight 请求、DNS rebinding
三类攻击向量。如果攻击者已经能在 micro-eval UI 的同源页面注入脚本（XSS），则
这些防护均不生效——但 XSS 防护属于 Next.js 框架层面的默认行为（React JSX 自动
转义），不在本设计文档范围内。

**读接口（GET）不做来源校验**——读操作在可信内网中不构成安全风险，且 GET 请求
本身不修改状态。

### 14.7 Data Isolation

- Workspace 之间通过目录隔离——workspace A 的 API 不能读 workspace B 的文件
  （path validation 保证）。
- 归属记录是**不可变的**（workspace.owner 创建后不可更改；run.json 的 owner 写入后
  不可修改）。但任何成员可以读任何 workspace（可信内网透明度原则）。

### 14.8 与 security-service-guidelines.md 的对齐

`security-service-guidelines.md` 已预留"未来服务化边界"章节，列出了 authentication、
tenant isolation、audit logging 等要求。Server 模式**部分覆盖**：

| 要求 | Server 模式覆盖 |
|------|-----------------|
| authentication | 不覆盖（可信内网假设，X-Micro-Eval-Member 自报） |
| tenant isolation | 部分覆盖（workspace 目录隔离，无系统级隔离） |
| audit logging | 部分覆盖（归属记录，无独立审计日志） |
| hosted sandbox | 不变（复用现有 provider registry） |
| secret storage | 不变（复用现有安全规范） |
| data retention | 不覆盖（手动删除） |
| abuse prevention | 部分覆盖（queue size limit、timeout） |
| CSRF protection | 覆盖（Content-Type 强制 + 自定义 header 检查 + 无 CORS，§14.6） |

当从"可信内网"迁移到"需要 auth 的场景"时，需要补充完整的服务安全规范。

---

## 15. Migration & Backward Compatibility

### 15.1 Existing Data

无数据迁移。现有 `.micro-eval/runs/` 目录不受影响。`micro-eval ui` 继续读本地数据。

### 15.2 从本地模式导入 workspace（v0.4.1 延后）

~~如果团队成员已经在本地跑了 run，可以把结果导入 server~~ ——`workspace import`
命令从 v0.4.0 范围中**移除**，延后到 v0.4.1。理由：import 涉及 legacy run.json
缺少 `owner`/`server_context` 字段的兼容处理、路径重映射、趋势索引重建，复杂度
超出 v0.4.0 的范围。

手动迁移方案（v0.4.0 可用）：运维通过 `micro-eval workspace create` 创建空白
workspace，然后手动 `cp -r` 本地 `.micro-eval/` 目录到 workspace 下。

### 15.3 CLAUDE.md 边界更新

v0.4 应更新 CLAUDE.md 的"MVP 不做"列表：

**Before**:
> MVP 不做：多团队协作、RBAC/SSO、复杂审计、大规模任务库、高级推荐引擎。

**After**:
> MVP 不做：RBAC/SSO、复杂审计、大规模任务库、高级推荐引擎。
> v0.4 新增：可信内网多成员共享 Server（workspace 隔离、串行队列、只读模板库、
> 归属记录），不含认证/权限控制。

**实施前置条件**（v0.4 开发开始前必须完成）：

1. **更新 CLAUDE.md 边界**：第一个 commit 必须更新 CLAUDE.md 的"MVP 不做"列表和
   "当前状态"段落，使权威边界文件与本设计文档对齐。这满足 CLAUDE.md 的硬规则——
   "先更新权威来源，再更新工程规范"。
2. **分支约束**：v0.4 仅在 `dev` 分支实施，发布到 `main` 只能通过 release 流程
   （merge dev → main）。不直接在 `main` 上开发。
3. **更新安全规范**：`docs/engineering/security-service-guidelines.md` 需新增
   "Team Server 服务化安全附录"，固化以下内容：trusted intranet 假设的边界条件、
   无 auth 的接受范围、`config_overrides` 白名单列表、归属记录作为最小审计要求。

---

## 16. Test Plan

### 16.1 Workspace（pytest）

| Test | What it verifies |
|------|-----------------|
| `test_workspace_create_from_template` | 模板内容正确复制到 workspace |
| `test_workspace_create_blank` | 空白 workspace 有 workspace.json + 空 eval.yaml |
| `test_workspace_id_format` | ID 格式 `ws-<timestamp>-<hex>` |
| `test_workspace_id_unique` | 同时创建的 workspace ID 不重复 |
| `test_workspace_lifecycle` | active → archived → deleted 状态流转 |
| `test_workspace_delete_removes_directory` | 删除 workspace 物理删除目录 |
| `test_workspace_path_validation` | 路径穿越尝试被拒绝 |
| `test_workspace_symlink_escape` | symlink 逃逸被拒绝 |
| `test_workspace_isolation` | workspace A 的 API 不能读 workspace B |

### 16.2 Template Registry（pytest）

| Test | What it verifies |
|------|-----------------|
| `test_template_create` | 从目录创建模板，template.json 正确 |
| `test_template_update_version` | 更新模板递增 version |
| `test_template_list` | 列出所有模板 |
| `test_template_delete` | 删除模板目录 |
| `test_template_readonly` | API 不提供模板写入接口 |
| `test_workspace_records_template_version` | workspace 记录创建时的 template_version |

### 16.3 Run Queue（pytest）

| Test | What it verifies |
|------|-----------------|
| `test_enqueue_creates_job` | 入队写入 queue.db |
| `test_dequeue_fifo` | 取出最早的 queued job |
| `test_dequeue_atomic` | 并发 dequeue 不重复取 |
| `test_job_lifecycle` | queued → running → done 状态流转 |
| `test_job_failure` | 执行失败标记 failed + error |
| `test_job_cancellation_queued` | 取消 queued job 立即标记 cancelled |
| `test_job_cancellation_running` | 取消 running job 设置 cancel_requested_at |
| `test_cancel_done_job_rejected` | 取消 done job 返回 409 |
| `test_cancel_sets_cancelled_by` | 取消操作记录 cancelled_by 字段 |
| `test_queue_overflow` | 达到 max_queue_size 时拒绝入队 |
| `test_crash_recovery_completed` | worker 重启时识别已完成但未标记的 job |
| `test_crash_recovery_interrupted` | worker 重启时标记中断的 job 为 failed |
| `test_progress_update` | worker 更新 progress 字段 |

### 16.4 Worker（pytest）

| Test | What it verifies |
|------|-----------------|
| `test_worker_calls_kernel` | worker 正确调用 ExecutionKernel.run |
| `test_worker_sets_project_root` | project_root 指向 workspace 目录 |
| `test_worker_writes_run_json` | run.json 写入 workspace 的 .micro-eval/runs/ |
| `test_worker_updates_job_status` | 执行完成后 job 状态正确 |
| `test_worker_records_owner` | run.json 的 owner 字段从 job 复制 |
| `test_worker_records_server_context` | server_context 写入 RunRecord |
| `test_worker_timeout` | 超时后标记 failed |
| `test_worker_serial` | 多个 job 串行执行（不并行） |

### 16.5 Server Launch（pytest）

| Test | What it verifies |
|------|-----------------|
| `test_serve_creates_data_root` | 首次启动创建 ~/.micro-eval-server/ |
| `test_serve_initializes_queue_db` | 创建 queue.db |
| `test_serve_starts_worker` | worker 子进程启动 |
| `test_serve_graceful_shutdown` | SIGTERM 先停 worker 再停 server |

### 16.6 Member Identity（pytest + vitest）

| Test | What it verifies |
|------|-----------------|
| `test_member_header_recorded` | X-Micro-Eval-Member 写入归属记录 |
| `test_member_header_missing` | 缺失时使用 anonymous |
| `test_member_name_validation` | 非法字符被拒绝 |
| `test_cancel_any_job` | 任何成员可以取消任何 job |
| `test_cancel_records_cancelled_by` | 取消操作记录 cancelled_by 字段 |

### 16.7 UI Data Layer（vitest）

| Test | What it verifies |
|------|-----------------|
| `test_server_mode_detection` | MICRO_EVAL_SERVER_MODE 环境变量检测 |
| `test_workspace_runs_dir` | workspace-scoped runs 目录解析 |
| `test_workspace_path_validation` | 路径穿越拒绝 |
| `test_evaluate_subprocess_cwd` | evaluate 的 cwd 指向 workspace |
| `test_legacy_mode_unchanged` | 非 server 模式行为不变 |

### 16.8 API Routes（vitest）

| Test | What it verifies |
|------|-----------------|
| `test_list_workspaces` | GET /api/workspaces 返回所有 active workspace |
| `test_create_workspace_from_template` | POST /api/workspaces 正确复制模板 |
| `test_create_workspace_blank` | POST /api/workspaces 无 template_id |
| `test_workspace_runs` | GET /api/workspaces/[id]/runs 返回 workspace 内的 run |
| `test_enqueue_run` | POST /api/workspaces/[id]/runs/enqueue 创建 job |
| `test_enqueue_invalid_workspace` | 不存在的 workspace 返回 404 |
| `test_queue_dashboard` | GET /api/queue 返回正确结构 |
| `test_job_status` | GET /api/jobs/[id] 返回 job 状态 |
| `test_server_routes_404_in_legacy` | 非 server 模式下 server routes 返回 404 |
| `test_config_get` | GET /api/workspaces/[id]/config 返回 eval.yaml |
| `test_config_put_valid` | PUT /api/workspaces/[id]/config 写入合法 YAML |
| `test_config_put_invalid` | PUT /api/workspaces/[id]/config 拒绝非法 YAML |

### 16.9 Contract Tests

| Test | What it verifies |
|------|-----------------|
| `test_workspace_json_roundtrip` | write → read → write 产生相同 JSON |
| `test_template_json_roundtrip` | 同上 |
| `test_queue_db_schema_forward_compat` | 额外字段不破坏读取 |
| `test_run_record_server_context_pydantic_zod_parity` | Python RunRecord.server_context ↔ TS RunRecordSchema parity |
| `test_workspace_schema_pydantic_zod_parity` | Python workspace.json schema ↔ TS WorkspaceSchema parity |
| `test_job_schema_pydantic_zod_parity` | Python job schema ↔ TS JobSchema parity |

### 16.10 Security Negative Tests（pytest + vitest）

| Test | What it verifies |
|------|-----------------|
| `test_workspace_id_path_traversal_dot_dot` | `../` 路径穿越被拒绝 |
| `test_workspace_id_null_byte` | 空字节注入被拒绝 |
| `test_config_overrides_whitelist_escape` | config_overrides 不能覆盖 agent command / workspace path |
| `test_config_overrides_command_injection` | config_overrides 不能注入 shell 命令 |
| `test_enqueue_archived_workspace_rejected` | archived workspace 不能入队新 run |
| `test_delete_workspace_with_pending_job_rejected` | 有 queued/running job 时拒绝删除 workspace |
| `test_archive_workspace_with_pending_job_rejected` | 有 queued/running job 时拒绝归档 workspace |
| `test_member_name_special_chars_rejected` | 非 `[a-zA-Z0-9._-]` 字符被拒绝 |
| `test_eval_yaml_body_size_limit` | PUT config 超过 1MB 被拒绝 |
| `test_symlink_escape_via_workspace_id` | symlink 逃逸再次被测试（server mode 路径） |
| `test_write_api_rejects_form_urlencoded` | 写接口拒绝 application/x-www-form-urlencoded |
| `test_write_api_rejects_text_plain` | 写接口拒绝 text/plain Content-Type |
| `test_write_api_requires_member_header` | 写接口缺少 X-Micro-Eval-Member 时返回 400 |
| `test_no_cors_headers_in_response` | 响应不包含 Access-Control-Allow-Origin |
| `test_host_header_allowlist_rejects_unknown` | 非 allowlist Host header 返回 400 |
| `test_host_header_dns_rebinding` | 攻击者域名作为 Host header 被拒绝 |

### 16.11 API Route Contract Tests（vitest）

| Test | What it verifies |
|------|-----------------|
| `test_workspace_api_response_matches_schema` | GET /api/workspaces/[id] 响应符合 WorkspaceSchema |
| `test_job_api_response_matches_schema` | GET /api/jobs/[id] 响应符合 JobSchema |
| `test_queue_api_response_matches_schema` | GET /api/queue 响应符合 QueueSchema |
| `test_template_api_response_matches_schema` | GET /api/templates/[id] 响应符合 TemplateSchema |
| `test_workspace_runs_api_matches_existing_contract` | workspace-scoped run API 与现有 run API 输出一致 |
| `test_enqueue_api_response_matches_schema` | POST enqueue 响应符合 EnqueueResponseSchema |

### 16.12 Worker E2E Tests（pytest）

| Test | What it verifies |
|------|-----------------|
| `test_worker_crash_and_restart_recovery` | 模拟 worker crash 后重启，running job 被正确标记 |
| `test_worker_duplicate_start_prevention` | 多个 worker 实例不会同时取同一 job |
| `test_run_timeout_enforcement` | 超时 run 被标记 failed |
| `test_workspace_delete_after_all_jobs_complete` | 所有 job 完成后可以正常删除 workspace |
| `test_cancel_during_run_stop_after_run` | cancel_requested_at 设置后，run 完成后 job 标记为 cancelled |
| `test_cancel_during_run_with_failure` | run 失败时 cancel_requested_at 被忽略，job 标记为 failed |
| `test_stale_pid_file_process_not_running` | PID 文件存在但进程已退出，worker 正常启动并覆盖 PID 文件 |
| `test_legacy_run_json_without_optional_fields` | 手动迁移的 legacy run.json（无 owner/server_context）在 server UI 中可读 |
| `test_crash_recovery_with_cancel_requested` | crash 恢复时 cancel_requested_at + completed run → 标记 cancelled 而非 done |

---

## 17. Implementation Boundaries

### 17.1 Files to Create

| File | Purpose |
|------|---------|
| `src/micro_eval/server/workspace.py` | WorkspaceManager: create/list/delete |
| `src/micro_eval/server/template.py` | TemplateRegistry: create/update/list/delete |
| `src/micro_eval/server/queue.py` | QueueDB: enqueue/dequeue/status/cancel |
| `src/micro_eval/server/worker.py` | Run worker 守护进程主循环 |
| `src/micro_eval/server/__init__.py` | Server package init |
| `src/micro_eval/cli/serve.py` | serve / worker CLI 命令 |
| `src/micro_eval/cli/workspace_cmd.py` | workspace create/list/delete CLI 命令 |
| `src/micro_eval/cli/template_cmd.py` | template create/update/list/delete CLI 命令 |
| `src/micro_eval/cli/build_plan.py` | build-plan CLI 子命令 |
| `src/micro_eval/cli/queue_cmd.py` | queue status/cancel CLI 命令 |
| `ui/src/lib/server-mode.ts` | Server mode detection + data root |
| `ui/src/lib/workspace-api.ts` | Workspace-scoped data access functions |
| `ui/src/app/workspace/[id]/page.tsx` | Workspace detail + run list |
| `ui/src/app/workspace/[id]/run/[runId]/page.tsx` | Run detail (workspace-scoped) |
| `ui/src/app/workspace/[id]/run/[runId]/review/page.tsx` | Review (workspace-scoped) |
| `ui/src/app/workspace/[id]/run/[runId]/artifact/[artifactId]/page.tsx` | Artifact (workspace-scoped) |
| `ui/src/app/workspace/[id]/config/page.tsx` | Config editor page |
| `ui/src/app/workspaces/page.tsx` | Workspace list page |
| `ui/src/app/workspaces/new/page.tsx` | Create workspace page |
| `ui/src/app/templates/page.tsx` | Template list page |
| `ui/src/app/templates/[id]/page.tsx` | Template detail page |
| `ui/src/app/queue/page.tsx` | Queue dashboard page |
| `ui/src/app/api/server/status/route.ts` | Server status endpoint |
| `ui/src/app/api/templates/route.ts` | Template list endpoint |
| `ui/src/app/api/templates/[id]/route.ts` | Template detail endpoint |
| `ui/src/app/api/workspaces/route.ts` | Workspace list + create endpoint |
| `ui/src/app/api/workspaces/[id]/route.ts` | Workspace detail/update/delete |
| `ui/src/app/api/workspaces/[id]/runs/route.ts` | Workspace runs list |
| `ui/src/app/api/workspaces/[id]/runs/[runId]/route.ts` | Run detail |
| `ui/src/app/api/workspaces/[id]/runs/[runId]/cells/[cellId]/route.ts` | Cell detail |
| `ui/src/app/api/workspaces/[id]/runs/[runId]/cells/[cellId]/evaluate/route.ts` | Evaluate |
| `ui/src/app/api/workspaces/[id]/runs/[runId]/cells/[cellId]/trace/route.ts` | Trace |
| `ui/src/app/api/workspaces/[id]/runs/[runId]/artifacts/route.ts` | Artifacts |
| `ui/src/app/api/workspaces/[id]/runs/enqueue/route.ts` | Enqueue run |
| `ui/src/app/api/workspaces/[id]/trends/route.ts` | Trends |
| `ui/src/app/api/workspaces/[id]/config/route.ts` | Config get/put |
| `ui/src/app/api/queue/route.ts` | Queue dashboard |
| `ui/src/app/api/jobs/[jobId]/route.ts` | Job status |
| `ui/src/app/api/jobs/[jobId]/cancel/route.ts` | Cancel job |
| `ui/src/components/WorkspaceCard.tsx` | Workspace card |
| `ui/src/components/WorkspaceList.tsx` | Workspace card grid |
| `ui/src/components/WorkspaceCreateForm.tsx` | Create workspace form |
| `ui/src/components/QueueDashboard.tsx` | Queue status panel |
| `ui/src/components/QueueJobCard.tsx` | Job status card |
| `ui/src/components/RunEnqueueButton.tsx` | Enqueue + poll + redirect |
| `ui/src/components/ConfigEditor.tsx` | eval.yaml editor |
| `ui/src/components/TemplateCard.tsx` | Template card |
| `ui/src/components/TemplateList.tsx` | Template card grid |
| `ui/src/components/MemberBadge.tsx` | Member name badge |

### 17.2 Files to Modify

| File | Change |
|------|--------|
| `src/micro_eval/cli/main.py` | Add serve/worker/workspace/template/build-plan/queue commands; update ui command |
| `src/micro_eval/engine/kernel.py` | Add optional `on_cell_complete` callback to __init__; call it in run() loop |
| `src/micro_eval/store/run_store.py` | Add optional `owner` and `server_context` to RunRecord; write them in finalize_run |
| `ui/src/lib/api.ts` | Add server mode check; refactor to parameterize runsDir source |
| `ui/src/lib/schema.ts` | Add WorkspaceSchema, TemplateSchema, JobSchema, QueueSchema |
| `ui/src/app/page.tsx` | Conditional: server dashboard (server mode) or project cards (legacy) |
| `ui/src/components/RunList.tsx` | Accept workspaceId prop for server mode link generation |
| `ui/src/components/CellDetail.tsx` | Accept workspaceId prop |
| `ui/src/components/MatrixHeatmap.tsx` | Accept workspaceId prop |
| `ui/src/components/AnnotationPanel.tsx` | POST URL uses workspace-scoped endpoint in server mode |
| `pyproject.toml` | Add server dependencies (if any); register new CLI entry points |
| `src/micro_eval/models/run.py` | Add optional `owner: str` and `server_context: ServerContext` fields to RunRecord |
| `ui/src/lib/schema.ts` | Extend RunRecordSchema with optional `owner` and `server_context` fields |

### 17.2.1 Schema 版本与兼容性策略

新增字段（`owner`、`server_context`）在 Python（Pydantic）和 TS（zod）两侧均为
**可选字段**，默认值为 `None`/`undefined`。这保证：

- 本地模式产生的 run.json（无 `owner`/`server_context`）在 server 模式 UI 中可读。
- Server 模式产生的 run.json 在本地模式 UI 中可读（多余字段被忽略）。
- `workspace.json`、`template.json` 都有 `schema_version` 字段，
  未来 schema 演进通过版本号控制。
- `queue.db` 通过 DDL 迁移脚本管理 schema 变更（`QueueDB.__init__` 运行
  `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`，
  向前兼容额外字段）。

Pydantic ↔ zod parity 由 `test_run_record_server_context_pydantic_zod_parity`
等 contract test 守护（§16.9）。

### 17.3 Out of Scope for v0.4.0

These are explicitly deferred and must NOT be implemented in v0.4.0:

- WebSocket for real-time job status push (polling is sufficient for 1-20 users).
- Parallel run execution (serial queue is the design choice).
- Template versioning UI (CLI-only management).
- Workspace sharing / transfer between members.
- Run comparison across workspaces (each workspace is independent).
- Mobile-responsive UI (desktop browser is the target).
- Automated workspace cleanup / retention policies.
- `workspace import` CLI 命令（延后到 v0.4.1，见 §15.2）。
- Running job 的 cell 级取消（v0.4 仅支持 stop-after-run，见 §7.8）。

---

## 18. Glossary

| Term | Definition |
|------|-----------|
| **Workspace** | Server 上的隔离评测环境，归属一个成员，包含 eval.yaml + .micro-eval/ |
| **Template** | 只读评测配置模板，成员创建 workspace 时从模板复制 |
| **Run Worker** | Python 常驻守护进程，串行执行 run queue 中的 job |
| **Job** | 队列中的一个 run 请求，包含 workspace_id、plan、status |
| **Member** | 通过 X-Micro-Eval-Member header 自报身份的团队成员 |
| **Server Mode** | `micro-eval serve` 启动的多成员共享模式，与 `micro-eval ui` 的本地单机模式并存 |
| **Data Root** | Server 模式的数据根目录，默认 `~/.micro-eval-server/` |
