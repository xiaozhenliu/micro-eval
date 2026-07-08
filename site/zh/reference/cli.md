# CLI 命令

`micro-eval` 全部命令参考。当前版本：**0.4.1**。

## 配置文件查找顺序

所有接受配置文件的命令均按以下顺序解析：

1. `--config PATH` 标志（显式覆盖）
2. `$MICRO_EVAL_CONFIG` 环境变量
3. 当前工作目录下的 `./eval.yaml`

::: tip
在项目根目录下运行所有命令，这样 `./eval.yaml` 会被自动找到。
:::

---

## micro-eval init

创建一个初始 `eval.yaml`、一个 `tasks/hello.yaml` 模板以及配套的任务脚手架。可在空目录或已有项目中安全运行。

**语法**

```
micro-eval init [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--force` | 标志 | `false` | 如果 `eval.yaml` 和任务文件已存在，则覆盖它们。 |

**生成的文件**

```
./
├── eval.yaml            # 根配置（configurations + 运行设置）
└── tasks/
    └── hello.yaml       # 包含一个 expectation 的入门任务
```

**示例**

::: code-group

```bash [首次使用]
# 为新项目生成脚手架
micro-eval init
```

```bash [重新生成]
# 覆盖已有文件（升级后很有用）
micro-eval init --force
```

:::

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 成功 — 文件已写入。 |
| `1` | 错误 — 目标文件已存在且未传入 `--force`，或文件系统错误。 |

---

## micro-eval validate

加载 `eval.yaml` 及所有被引用的任务文件，解析完整的 RunPlan（Tasks × Configurations × Repetitions），并输出诊断信息。**不会调用任何 agent。**

在每次 `run` 之前使用此命令，可以提前发现 schema 错误、缺失的任务文件或 workspace spec 配置错误。

**语法**

```
micro-eval validate [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--config PATH` | path | _（查找顺序）_ | 根配置文件路径。 |
| `--format` | `text` \| `json` | `text` | 输出格式。在 CI 中使用 `json` 可获得机器可读的诊断信息。 |

**检查内容**

- `eval.yaml` 能通过 Pydantic schema 解析，无报错。
- `tasks:` 下引用的每个任务文件存在且有效。
- 每个 `WorkspaceSpec` 拥有可访问的 `git_repo`（`git_repo` 类型）或有效的文件列表。
- 所有 `expectations` 引用的类型受支持：`exit_code`、`contains`、`file_exists` 或 `command`。
- 隔离级别在当前平台可用（若 Seatbelt/Bubblewrap 不存在则发出警告并回退到 `logical`）。

**示例**

::: code-group

```bash [默认文本输出]
micro-eval validate
```

```bash [CI 使用 JSON 输出]
micro-eval validate --format json
```

```bash [显式指定配置路径]
micro-eval validate --config ./experiments/finetune.yaml
```

:::

**文本输出示例**

```
✓ Config loaded: eval.yaml
✓ Tasks: 3 found, 3 valid
✓ Configurations: 2
✓ RunPlan: 6 cells (3 tasks × 2 configs × 1 repetition)
✓ Workspace: git_repo @ HEAD (sha: a1b2c3d)
⚠ Isolation: seatbelt not found — falling back to logical (git worktree)
```

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | RunPlan 有效，可以执行。 |
| `1` | 意外错误（文件系统、导入失败）。 |
| `2` | 校验失败 — schema 错误或文件缺失；详情输出到 stderr。 |

---

## micro-eval run

执行完整的评测矩阵：**Tasks × Configurations × Repetitions**。每个 cell 都是对被测 agent 的一次子进程调用。结果写入 `.micro-eval/runs/<run-id>/`。

**语法**

```
micro-eval run [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--config PATH` | path | _（查找顺序）_ | 根配置文件路径。 |
| `--max-concurrency N` | int | `4` | 同时运行的 agent 子进程最大数量。 |
| `--dry-run` | 标志 | `false` | 打印已解析的 RunPlan 后退出，不调用任何 agent。 |
| `--format` | `text` \| `json` | `text` | 进度和摘要的输出格式。 |

**执行模型**

- RunPlan 展开为一个有序的 `(task, config, repetition)` cell 列表。
- Cell 在 `asyncio` 下运行，受 `--max-concurrency` 控制并发上限。
- 每个 agent 仅通过 `argv` 传参，**不进行 shell 字符串插值**。
- 匹配 `MICRO_EVAL_SECRET_*` 的 secrets 会传递到子进程环境，但在所有日志和存储的 artifact 中**自动脱敏**。
- 执行完成后，确定性校验器检查 `expectations`；如已配置，可选的 LLM judge 也会运行。

**隔离级别**（在运行时解析）

| 级别 | 机制 | 平台 |
|------|------|------|
| `logical` | 每个 cell 使用 git worktree | 全平台 |
| `os_policy` | Seatbelt（macOS）/ Bubblewrap（Linux） | macOS / Linux |
| `container` | 容器运行时 | 需要 Docker 或等效工具 |
| `vm` | E2B / Modal 远程沙箱 | 需要凭证 |

::: warning
如果请求 `os_policy` 隔离但平台二进制文件不可用，执行将回退到 `logical` 并在运行结果中记录一条 caveat。远程 provider（`vm`）**不会回退** — 若凭证缺失则直接报错。
:::

**示例**

::: code-group

```bash [默认运行]
micro-eval run
```

```bash [降低并发数]
# 当 agent 内存占用较高时使用
micro-eval run --max-concurrency 2
```

```bash [Dry run — 检查计划而不执行]
micro-eval run --dry-run
```

```bash [CI 使用 JSON 输出]
micro-eval run --format json
```

```bash [自定义配置]
micro-eval run --config ./experiments/finetune.yaml --max-concurrency 8
```

:::

**传递 secrets**

```bash
# Secrets 会被转发给 agent 子进程，并从所有日志中脱敏
export MICRO_EVAL_SECRET_API_KEY=sk-...
micro-eval run
```

**输出位置**

```
.micro-eval/
└── runs/
    └── <run-id>/
        ├── run.json          # RunResult（scores、decisions、caveats）
        ├── matrix.json       # 完整 ResultMatrix
        └── artifacts/        # 每个 cell 的 stdout、stderr、diffs
```

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 所有 cell 已完成（部分 cell 的得分可能为 0；请检查矩阵）。 |
| `1` | 执行错误 — agent 启动失败、文件系统错误或未处理的异常。 |
| `2` | 校验失败 — 配置或任务 schema 错误导致运行未能启动。 |

---

## micro-eval list

列出 `.micro-eval/runs/*/run.json` 下发现的运行记录。可用于查找传递给 `micro-eval report` 的 `RUN_ID`。

**语法**

```
micro-eval list [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--format` | `text` \| `json` | `text` | 输出格式。 |

**示例**

::: code-group

```bash [人类可读的表格]
micro-eval list
```

```bash [机器可读的列表]
micro-eval list --format json
```

:::

**文本输出示例**

```
RUN ID                                STARTED              TASKS  CONFIGS  STATUS
run-20260615-143022-a1b2c3d4          2026-06-15 14:30:22      3        2  complete
run-20260614-091045-f9e8d7c6          2026-06-14 09:10:45      5        2  complete
run-20260613-172300-11223344          2026-06-13 17:23:00      3        3  partial
```

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 列表已打印（若没有运行记录则为空）。 |
| `1` | 错误 — `.micro-eval/` 目录不存在或不可读。 |

---

## micro-eval report

渲染已完成运行的 ResultMatrix，包括每个 cell 的得分、聚合统计、总体 decision、caveats 以及 artifact 引用。

**语法**

```
micro-eval report [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--run RUN_ID` | string | _（最新运行）_ | 来自 `micro-eval list` 的运行标识符。默认为最近一次运行。 |
| `--format` | `text` \| `json` \| `html` | `text` | 输出格式。`html` 会写入一个独立的报告文件。 |
| `--output PATH` | path | `report.html` | 使用 `--format html` 时的目标文件路径。 |

**Decision 状态**

| 状态 | 含义 |
|------|------|
| `improved` | 新配置在所有任务上得分更高。 |
| `regressed` | 新配置在所有任务上得分更低。 |
| `mixed` | 部分任务改善，部分任务退步。 |
| `inconclusive` | 差异在噪声阈值以内。 |
| `not_comparable` | 两次运行使用了不同的 workspace 快照或任务集。 |
| `needs_human_review` | LLM judge 置信度低于阈值；需要人工标注。 |

**示例**

::: code-group

```bash [最新运行，文本格式]
micro-eval report
```

```bash [指定运行，JSON 格式]
micro-eval report --run run-20260615-143022-a1b2c3d4 --format json
```

```bash [HTML 报告输出到文件]
micro-eval report --format html --output ./reports/2026-06-15.html
```

```bash [HTML 输出到自定义路径]
micro-eval report \
  --run run-20260615-143022-a1b2c3d4 \
  --format html \
  --output /tmp/eval-report.html
```

:::

**文本输出示例**

```
Run: run-20260615-143022-a1b2c3d4  (2026-06-15 14:30:22)
Tasks: 3  Configurations: 2  Repetitions: 1

                       config-baseline   config-new
  task: summarize           0.82            0.91  ▲
  task: classify            0.74            0.68  ▼
  task: extract             0.90            0.90  —

Decision: mixed
Caveats:
  - Isolation fell back to logical (seatbelt unavailable)
  - LLM judge used for task:summarize (deterministic score N/A)
```

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 报告渲染成功。 |
| `1` | 错误 — 运行 ID 未找到，或输出路径不可写。 |
| `2` | 运行数据损坏或缺少必填字段。 |

---

## micro-eval apply-evaluation

将一次人工评测应用到某个运行 cell，并重新计算该运行的 decision。从 stdin 读取 JSON payload，将得到的 evaluation、evidence 与更新后的 decision 以 JSON 形式写入 stdout。这与 Web UI 复核页面在审核者提交 pass/fail 判定时走的是同一条代码路径——同时也可直接用于脚本或 CI。

**语法**

```
micro-eval apply-evaluation --run-id RUN_ID --cell-id CELL_ID
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--run-id` | string | _（必填）_ | 来自 `micro-eval list` 的运行标识符。 |
| `--cell-id` | string | _（必填）_ | 运行的 ResultMatrix 中的 cell 标识符。 |

**Stdin payload**

| 字段 | 类型 | 描述 |
|------|------|------|
| `pass_fail` | boolean | 该 cell 的总体 pass/fail 判定。 |
| `score` | number | 可选的单一标量得分。 |
| `scores` | object | 可选的分维度得分。 |
| `comment` | string | 审核者评论。 |
| `evaluator` | string | 审核者身份，默认为 `"human"`。 |

**示例**

::: code-group

```bash [提交带评论的 pass 判定]
echo '{"pass_fail": true, "comment": "Matches rubric", "evaluator": "alice"}' \
  | micro-eval apply-evaluation --run-id run-20260615-143022-a1b2c3d4 --cell-id cell-003
```

:::

**输出示例**

```json
{"evaluation": {...}, "evidence": {...}, "decision": {...}}
```

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 评测应用成功，decision 已重新计算。 |
| `1` | stdin 上的 JSON 无效，或运行/cell 未找到。 |

---

## micro-eval ui

启动本地 Next.js Web UI。UI 直接从 `.micro-eval/` JSON 文件读取运行数据，不会向外部传输任何数据。

::: warning
`micro-eval ui` 需要包含 `ui/` 目录的仓库源码检出，并已安装 Node.js 依赖（`cd ui && npm install`）。仅通过 pip 安装时此命令不可用。
:::

**语法**

```
micro-eval ui [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--port N` | int | `3000` | Next.js 开发服务器的本地端口。 |

**环境变量**

| 变量 | 描述 |
|------|------|
| `MICRO_EVAL_PROJECT_ROOT` | UI 应读取其 `.micro-eval/` 目录的项目绝对路径。默认为当前工作目录。 |

**示例**

::: code-group

```bash [默认端口]
micro-eval ui
```

```bash [自定义端口]
micro-eval ui --port 4000
```

```bash [指向另一个项目]
MICRO_EVAL_PROJECT_ROOT=/path/to/my-agent-project micro-eval ui --port 3000
```

:::

启动后，在浏览器中打开 [http://localhost:3000](http://localhost:3000)。

::: tip
当新的运行完成时，UI 会热重载。你可以在一个终端标签页中保持 UI 运行，同时在另一个标签页中运行 `micro-eval run`。
:::

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 服务器正常停止（例如 Ctrl-C）。 |
| `1` | 错误 — `ui/` 目录未找到、Node.js 未安装，或端口已被占用。 |

---

## 团队服务器命令

以下命令需要 v0.4.0+，用于管理共享内网服务器、workspace、模板和运行队列。所有 `--data-root` 选项的默认值均为 `~/.micro-eval-server`。

::: tip 仅限内网使用
团队服务器**没有认证机制，也没有 RBAC**。它为私有网络上 1–20 人的受信团队而设计。请勿在公网接口上暴露该服务器。
:::

---

### micro-eval serve

启动团队服务器：将 Next.js 前端和 Python 运行 worker 作为两个协同进程运行。这是团队共享使用的主要入口。

**语法**

```
micro-eval serve [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--port N` | int | `3000` | Next.js 服务器的端口。 |
| `--host HOST` | string | `0.0.0.0` | Next.js 服务器的绑定地址。 |
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器侧数据的根目录（workspace、队列、模板）。 |

**描述**

`micro-eval serve` 同时启动两个进程并保持它们运行。停止时（Ctrl-C）会同时关闭两个进程。如需独立管理 worker，可用 `micro-eval serve` 启动前端，用 `micro-eval worker` 启动 worker。

**示例**

::: code-group

```bash [默认]
micro-eval serve
```

```bash [自定义端口]
micro-eval serve --port 8080
```

```bash [自定义数据根目录]
micro-eval serve --data-root /srv/micro-eval
```

:::

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 两个进程均已正常停止。 |
| `1` | 错误——端口已被占用、数据根目录不可写，或缺少 Node.js。 |

---

### micro-eval worker

将运行 worker 作为独立进程启动。worker 从 SQLite 队列中取出任务并逐一执行（run 内部的 cell 仍使用 `--max-concurrency`）。

**语法**

```
micro-eval worker [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--data-root PATH` | path | `~/.micro-eval-server` | 与服务器共享的根目录。 |

**描述**

在双进程模式下，在一个终端运行 `micro-eval serve --port N`，在另一个终端运行 `micro-eval worker`。worker 轮询 SQLite 队列（`<data-root>/queue.db`）以获取新任务。队列始终只有**一个** worker——所有 run 串行执行。

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | worker 正常停止。 |
| `1` | 错误——`data-root` 未找到或队列数据库不可访问。 |

---

### micro-eval workspace create

在服务器数据根目录下创建新的 workspace。

**语法**

```
micro-eval workspace create [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--name TEXT` | string | _（必填）_ | 人类可读的 workspace 名称。 |
| `--owner TEXT` | string | _（必填）_ | workspace 所有者的成员标识。 |
| `--template ID` | string | `null` | 用于初始化 workspace 的模板 ID。 |
| `--description TEXT` | string | `null` | 可选描述。 |
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

**示例**

```bash
micro-eval workspace create --name "PR Review Eval" --owner alice --template claude-code-v1
```

---

### micro-eval workspace list

列出所有 workspace。

**语法**

```
micro-eval workspace list [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--all` | 标志 | `false` | 包含已归档的 workspace。 |
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

---

### micro-eval workspace update

更新 workspace 元数据。

**语法**

```
micro-eval workspace update WORKSPACE_ID [OPTIONS]
```

**参数**

| 参数 | 描述 |
|------|------|
| `WORKSPACE_ID` | Workspace 标识符。 |

**选项**

| 选项 | 类型 | 描述 |
|------|------|------|
| `--name TEXT` | string | 新 workspace 名称。 |
| `--description TEXT` | string | 新描述。 |
| `--status STATUS` | `active` \| `archived` | 生命周期状态。 |
| `--data-root PATH` | path | 服务器数据根目录。 |

---

### micro-eval workspace delete

删除 workspace 及其所有运行数据。**不可恢复。**

**语法**

```
micro-eval workspace delete WORKSPACE_ID [OPTIONS]
```

**参数**

| 参数 | 描述 |
|------|------|
| `WORKSPACE_ID` | Workspace 标识符。 |

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--force` | 标志 | `false` | 跳过确认提示。 |
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

---

### micro-eval template create

从本地目录创建模板。模板创建后为只读；如需替换内容，请使用 `template update`。

**语法**

```
micro-eval template create SOURCE_DIR [OPTIONS]
```

**参数**

| 参数 | 描述 |
|------|------|
| `SOURCE_DIR` | 包含模板文件的本地目录路径。 |

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--id ID` | string | _（必填）_ | 唯一模板标识符（slug）。 |
| `--name TEXT` | string | _（必填）_ | 人类可读的模板名称。 |
| `--description TEXT` | string | `null` | 可选描述。 |
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

**示例**

```bash
micro-eval template create ./my-eval-template --id claude-code-v1 --name "Claude Code v1"
```

---

### micro-eval template update

用本地目录中的新版本替换模板内容。

**语法**

```
micro-eval template update TEMPLATE_ID SOURCE_DIR [OPTIONS]
```

**参数**

| 参数 | 描述 |
|------|------|
| `TEMPLATE_ID` | 模板标识符。 |
| `SOURCE_DIR` | 更新后的模板目录路径。 |

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

---

### micro-eval template list

列出所有模板。

**语法**

```
micro-eval template list [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

---

### micro-eval template delete

删除模板。从该模板创建的 workspace 不受影响。

**语法**

```
micro-eval template delete TEMPLATE_ID [OPTIONS]
```

**参数**

| 参数 | 描述 |
|------|------|
| `TEMPLATE_ID` | 模板标识符。 |

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

---

### micro-eval build-plan

从 `eval.yaml` 构建 `RunPlan` 并将解析后的 JSON 输出到 stdout。服务器入队任务时在内部使用；也可用于调试。

**语法**

```
micro-eval build-plan [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--workspace ID` | string | _（必填）_ | 用于解析计划的 workspace ID。 |
| `--overrides JSON` | string | `null` | 在 workspace 的 `eval.yaml` 之上应用的字段覆盖 JSON 字符串。 |

**示例**

```bash
micro-eval build-plan --workspace ws-abc123 | jq '.cells | length'
```

---

### micro-eval queue status

显示运行队列的当前状态。

**语法**

```
micro-eval queue status [OPTIONS]
```

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

**输出示例**

```
Queue: 2 queued, 1 running, 14 done
Running: job-20260619-001 (workspace: ws-abc123, owner: alice, started 4m ago)
Queued:
  job-20260619-002  ws-def456  bob   enqueued 2m ago
  job-20260619-003  ws-ghi789  carol enqueued 1m ago
```

---

### micro-eval queue cancel

取消排队或运行中的任务。

**语法**

```
micro-eval queue cancel JOB_ID [OPTIONS]
```

**参数**

| 参数 | 描述 |
|------|------|
| `JOB_ID` | 来自 `micro-eval queue status` 的任务标识符。 |

**选项**

| 选项 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--data-root PATH` | path | `~/.micro-eval-server` | 服务器数据根目录。 |

**描述**

对于**排队中**的任务，取消立即生效。对于**运行中**的任务，将记录取消请求；worker 完成当前 cell 后停止，任务状态变为 `cancelled`。

**退出码**

| 代码 | 含义 |
|------|------|
| `0` | 取消请求已记录。 |
| `1` | 任务 ID 未找到，或任务已处于终态（`done`、`failed`、`cancelled`）。 |

---

## 全局选项

以下选项被所有命令接受：

| 选项 | 描述 |
|------|------|
| `--help` | 显示帮助文本并退出。 |
| `--version` | 打印 `micro-eval` 版本并退出。 |

```bash
micro-eval --version
# micro-eval 0.4.1
```

---

## 环境变量参考

| 变量 | 使用者 | 描述 |
|------|--------|------|
| `MICRO_EVAL_CONFIG` | 所有命令 | 未传入 `--config` 时的默认配置路径。 |
| `MICRO_EVAL_PROJECT_ROOT` | `ui` | UI 读取其 `.micro-eval/` 的根目录。 |
| `MICRO_EVAL_SECRET_*` | `run` | 转发给 agent 子进程的 secrets；从日志中自动脱敏。 |
| `LANGFUSE_PUBLIC_KEY` | `run` | 可选的 Langfuse 可观测性（cost/latency tracing）。 |
| `LANGFUSE_SECRET_KEY` | `run` | 可选的 Langfuse 可观测性。 |
| `LANGFUSE_HOST` | `run` | 可选的 Langfuse host 覆盖。 |

::: danger
永远不要在 `eval.yaml` 中硬编码 secrets。请使用 `MICRO_EVAL_SECRET_*` 环境变量。它们会自动从所有存储的 artifact 和日志输出中脱敏。
:::

---

## 快速参考

```bash
# 生成脚手架
micro-eval init

# 运行前校验
micro-eval validate

# 执行
micro-eval run --max-concurrency 4

# 查找运行 ID
micro-eval list

# 读取报告
micro-eval report --run <RUN_ID> --format html --output report.html

# 打开本地 Web UI
micro-eval ui

# --- 团队服务器（v0.4.0+）---

# 启动团队服务器（Next.js + worker）
micro-eval serve --port 3000

# 管理 workspace
micro-eval workspace create --name "My Eval" --owner alice
micro-eval workspace list
micro-eval workspace update <WORKSPACE_ID> --status archived

# 管理模板（仅 CLI，浏览器中为只读）
micro-eval template create ./my-template --id my-tmpl --name "My Template"
micro-eval template list

# 查看队列
micro-eval queue status
micro-eval queue cancel <JOB_ID>
```
