# 团队服务器

micro-eval 的团队服务器将单台机器变成团队共享的评测服务器。团队成员通过浏览器访问、创建隔离工作区并提交运行任务——服务器以串行方式处理执行，避免资源竞争。

::: tip 何时使用服务器模式
当团队（1–20 人）有以下需求时，使用 `micro-eval serve`：
- 共享评测结果，无需在机器之间复制文件
- 使用公共模板库保持 eval 配置的一致性
- 通过浏览器提交运行任务，而不是 SSH 到机器上操作
- 记录谁运行了什么（归因记录）
:::

::: warning 仅限内网使用
服务器没有身份验证机制。请勿将其暴露到公网。所有团队成员均被信任可以如实自报身份。
:::

## 架构

服务器在单台机器上以两个协作进程运行：

- **Next.js 服务器** — 提供浏览器 UI 和 REST API，负责工作区和模板管理，并将运行任务写入队列
- **Python worker** — 从队列读取任务并使用 `ExecutionKernel` 执行运行，与 `micro-eval ui` 使用的是同一引擎

```
浏览器 → Next.js 服务器 → queue.db ← Python Worker → ExecutionKernel
                ↕                              ↕
        ~/.micro-eval-server/workspaces/<ws-id>/.micro-eval/runs/
```

队列数据库（`queue.db`）是一个 SQLite WAL 模式文件。Python worker 每次处理一个运行任务。单次运行内部的各单元格仍遵循工作区 `eval.yaml` 中的 `max_concurrency` 设置。

两个进程由同一条命令启动，共享同一个数据根目录。Next.js 服务器不直接调用 Python worker——通信完全通过队列数据库进行。

## 快速开始

```bash
# 在默认端口启动团队服务器
micro-eval serve

# 指定端口
micro-eval serve --port 3000

# 使用自定义数据目录（适用于挂载卷或 CI 机器）
micro-eval serve --data-root /data/eval-server --port 8080
```

首次启动时，`micro-eval serve` 会创建数据根目录并初始化其结构：

```
~/.micro-eval-server/
├── server.json        ← 服务器配置（端口、数据根目录、创建时间）
├── queue.db           ← SQLite WAL 队列
├── worker.pid         ← Python worker PID（worker 停止时不存在）
├── workspaces/        ← 每个工作区一个目录
└── templates/         ← 只读模板注册表
```

停止服务器时，发送 `SIGINT`（Ctrl-C）。Next.js 进程立即退出；Python worker 在完成当前运行单元格后停止，不会丢失任何运行数据。

::: tip 构建新鲜度检查
如果 `ui/.next` 下已存在 Next.js 构建产物，`micro-eval serve` 会比较其 `BUILD_ID` 时间戳与 UI 源文件的时间戳。如果任何源文件比构建产物更新，会在 stderr 打印警告：

```
Warning: UI sources are newer than the last build. Run 'cd ui && npm run build' to update.
```

这个检查不会阻塞启动——服务器仍会使用现有（过期）的构建产物启动。如果完全没有构建产物，`micro-eval serve` 会在启动前自动构建，构建失败时会直接报错退出。
:::

## 工作区

**工作区**是 `~/.micro-eval-server/workspaces/<ws-id>/` 下的一个隔离目录。它作为 `ExecutionKernel` 的 `project_root`——拥有自己的 `eval.yaml`、`.micro-eval/runs/` 和 `tasks/` 目录，与其他所有工作区完全独立。

成员可以通过浏览器或 CLI 创建工作区。每个工作区归创建它的成员所有，但任何成员都可以向任意工作区提交运行任务。

### 生命周期

| 状态 | 含义 |
|------|------|
| `active` | 正常状态。可以提交运行任务。 |
| `archived` | 只读。保留运行历史；不能提交新的运行任务。 |
| `deleted` | 已计划删除。有待处理队列任务时无法删除。 |

### CLI 管理

```bash
# 创建工作区（可选择从模板创建）
micro-eval workspace create --name "agent-comparison-q3" --owner alice --template baseline-eval

# 列出所有工作区
micro-eval workspace list

# 归档工作区（保留运行历史，禁止新的运行任务）
micro-eval workspace update <ws-id> --status archived

# 删除工作区（有待处理队列任务时失败）
micro-eval workspace delete <ws-id>
```

### 物理目录结构

```
~/.micro-eval-server/workspaces/<ws-id>/
├── workspace.json     ← 元数据（名称、所有者、状态、创建时间）
├── eval.yaml          ← 评测配置
├── tasks/             ← task YAML 文件
└── .micro-eval/
    └── runs/          ← 运行 JSON 文件（权威数据源）
```

## 模板

**模板**是 `~/.micro-eval-server/templates/` 中的一个只读快照。模板保存一份已知良好的 `eval.yaml` 及其关联的 task 文件，使新工作区能从一致的基线出发。

成员从模板创建工作区时，micro-eval 会将模板内容**复制**到新的工作区目录。工作区创建后立即独立——此后对模板的修改不会影响已有工作区，工作区的修改也不会影响模板。

模板只能通过 CLI 管理，不能通过浏览器操作。

```bash
# 将一个目录注册为模板
micro-eval template create ./my-eval-config --id baseline-eval --name "Baseline Eval"

# 列出可用模板
micro-eval template list

# 更新模板（不影响已有工作区）
micro-eval template update baseline-eval ./my-eval-config-v2

# 删除模板（不影响已有工作区）
micro-eval template delete baseline-eval
```

::: tip 模板更新不会自动传播
更新模板对已从该模板创建的工作区没有影响。如果希望现有工作区获取新的 task 文件，需手动将文件复制到每个工作区，或从更新后的模板创建新工作区。
:::

### Demo 模板

首次启动且模板注册表为空时，`micro-eval serve` 会自动创建一个名为 `demo-codefix` 的 demo 模板（"Demo: Codefix Showdown (mock agents, free)"）。仅当注册表中一个模板都没有时才会创建，因此不会覆盖或重复创建管理员已经建好的模板。

该 demo 模板使用一个确定性的 mock agent（一段普通的 Python 脚本，不调用任何 LLM）来修复一个小型 ledger 函数中的四舍五入 bug——这是一个可以端到端跑通、**零 API 成本**的自包含任务。它的作用是提供一个可直接体验的示例：从 `demo-codefix` 创建工作区并提交一次运行任务，即可看到完整流程（工作区 → 队列 → `ExecutionKernel` → 结果），无需任何 API key，也不产生任何费用。

## 运行队列

运行任务从浏览器提交，由 Python worker 串行执行。当多个成员同时提交运行任务时，这能防止机器过载。

### 任务状态

| 状态 | 含义 |
|------|------|
| `queued` | 等待 worker 处理 |
| `running` | 正在 `ExecutionKernel` 中执行 |
| `done` | 成功完成 |
| `failed` | 以错误终止 |
| `cancelled` | 在执行前或执行过程中被取消 |

### 提交运行任务

提交运行任务只能通过浏览器操作，没有对应的 CLI 命令。导航到一个工作区并点击**提交运行任务**。如果你还没有设置成员名称（见[成员身份](#成员身份)），UI 会先要求你设置。

在真正提交之前，一张确认卡片（"Run Preview"）会展示即将提交的内容：

- 单元格数量，格式为 `{task 数} task(s) × {配置数} config(s) × {重复次数} rep(s) = {总数} cell(s)`
- 将要执行的 agent 命令

确认预览内容后点击**确认并提交（Confirm & Enqueue）**即可提交，或点击**取消（Cancel）**放弃本次提交。如果预览数据加载失败，卡片仍允许你继续提交——它会提示你可以在没有预览的情况下提交。

提交成功后，任务处于 `queued` 或 `running` 状态时，UI 会显示实时队列位置和进度指示。页面通过轮询获取状态更新——不需要 WebSocket 连接。

CLI 的 `queue` 子命令只支持只读/管理类操作——查看状态和取消任务（见[取消语义](#取消语义)）——不支持提交新的运行任务。

### 取消语义

- **排队中的任务**立即取消——在 worker 处理之前，记录就从队列中移除。
- **运行中的任务**在当前运行单元格完成后收到取消信号。Worker 不会强制中断正在执行的单元格，而是在开始下一个单元格前停止。已完成的单元格结果会保留在运行结果中。

### 崩溃恢复

如果 Python worker 在某个任务处于 `running` 状态时崩溃，worker 会在下次启动时将该任务标记为 `failed`，并附上 `worker_crash` 错误信息。已完成单元格的运行数据不会丢失——部分结果会照常写入 `.micro-eval/runs/`。

## 成员身份

服务器使用自报身份进行归因。成员在每个写操作请求中通过 `X-Micro-Eval-Member` HTTP 头发送自己的身份标识。

### 身份组件

浏览器 UI 在导航栏中提供一个持久化的身份组件，紧挨着"工作区 / 队列 / 模板"链接。设置名称前它显示"Set your name"；点击后会切换为一个内联编辑框，输入名称并保存。名称保存在浏览器的 `localStorage` 中，之后访问会自动带出——不涉及服务端账号或登录。

这个保存的名称就是 UI 在每个写操作请求（创建工作区、提交或取消运行任务、创建或更新模板）中发送的 `X-Micro-Eval-Member` header 值。如果你还没设置名称，需要该 header 的操作（例如提交运行任务）会先提示你设置。

### 格式

- 1–64 个字符
- 允许的字符：`[a-zA-Z0-9._-]`
- 示例：`alice`、`bob.smith`、`team-lead`

### 使用场景

| 操作 | 是否必须提供 Header |
|------|-------------------|
| GET 请求（只读） | 否——默认为 `anonymous` |
| 创建工作区 | 是 |
| 提交运行任务 | 是 |
| 取消运行任务 | 是 |
| 创建/更新模板 | 是 |

成员名称会存储在工作区元数据中，并作为 `owner` 及记录在 `server_context` 溯源字段中。它会显示在 UI 的运行历史和工作区详情页面中。

::: warning 身份是自报的，不经验证
任何成员都可以声称任何名称。该 Header 的作用是归因和审计追踪，而非访问控制。如果某成员填写了错误的身份，他们可能会错误地归因某些运行，但不会因此获得任何额外的权限。
:::

## 安全模型

服务器专为受信任的内网环境设计。其安全模型包含四个层次：

### CSRF 防护

所有变更状态的 endpoint 都要求：

1. **`Content-Type: application/json`** — 普通 HTML 表单提交（常见的 CSRF 攻击向量）会被拒绝
2. **`X-Micro-Eval-Member` 自定义 Header** — 浏览器在没有 CORS 授权的情况下，无法在跨域请求中设置自定义 Header
3. **不设置宽松的 CORS Header** — 服务器不响应 `Access-Control-Allow-Origin: *`
4. **`Host` Header 白名单** — 来自未预期 `Host` 值的请求会被拒绝

### `config_overrides` 白名单

成员提交运行任务时可以传入 `config_overrides`，以修改部分配置参数（例如 `max_concurrency`、`timeout_s`）。服务器会严格执行可覆盖字段的白名单。可能影响工作区边界、provider 选择或 secrets 处理的字段不可被覆盖。

### 路径遍历防护

所有工作区和模板路径在执行任何文件操作前都会在数据根目录内解析和验证。解析后超出 `~/.micro-eval-server/` 范围的路径会以 `400` 错误被拒绝。

### 工作区隔离

每个工作区目录都是自包含的。`ExecutionKernel` 以工作区路径作为 `project_root`，在运行期间无法读写其外部的内容。这与 `micro-eval ui` 针对本地 `project_root` 运行时提供的隔离保障相同。

有关运行内部 OS 级别和 VM 级别沙箱的说明，请参阅 [Workspace 与沙箱](/zh/guide/workspace-isolation)。

## 数据目录

```
~/.micro-eval-server/
├── server.json            ← { port, data_root, created_at, version }
├── queue.db               ← SQLite WAL 数据库
│   └── (表：jobs, job_events)
├── worker.pid             ← Python worker PID 文件
├── workspaces/
│   ├── <ws-id-1>/
│   │   ├── workspace.json
│   │   ├── eval.yaml
│   │   ├── tasks/
│   │   └── .micro-eval/runs/
│   └── <ws-id-2>/
│       └── ...
└── templates/
    ├── baseline-eval/
    │   ├── template.json
    │   ├── eval.yaml
    │   └── tasks/
    └── ...
```

`.micro-eval/runs/` 下的 JSON 运行文件是权威数据源——与 `micro-eval ui` 产生的文件格式完全相同。SQLite 队列和索引是派生数据，可以从 JSON 文件重建。

## 与本地模式的对比

| 方面 | `micro-eval ui` | `micro-eval serve` |
|------|-----------------|-------------------|
| 使用者 | 个人在自己的机器上使用 | 团队共享的机器 |
| 数据位置 | `<project_root>/.micro-eval/` | `~/.micro-eval-server/workspaces/<ws-id>/` |
| 浏览器访问 | 仅限 `localhost` | 网络内任意机器 |
| 运行触发方式 | 本地 CLI 或浏览器 | 从浏览器提交，由后台 worker 执行 |
| 并发方式 | 立即执行 | 串行队列（每次一个运行任务） |
| 工作区 | 每个项目根目录一个 | 每台服务器可有多个命名工作区 |
| 模板 | 不支持 | 只读共享库 |
| 身份标识 | 不支持 | 通过 `X-Micro-Eval-Member` 自报 |
| 身份验证 | 无（仅限本地） | 无（内网信任模型） |

## 下一步

- [Workspace 与沙箱](/zh/guide/workspace-isolation) — agent 执行的隔离级别、信任级别和网络策略
- [安全模型](/zh/guide/security) — 完整安全参考，包括 secrets 处理和路径验证
- [CLI 命令](/zh/reference/cli) — `micro-eval serve`、`workspace`、`template` 和 `queue` 子命令的完整参考
