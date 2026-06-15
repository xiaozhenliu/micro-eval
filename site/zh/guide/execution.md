# 执行

micro-eval 通过将声明式配置展开为隔离运行的矩阵、并发执行每个单元格并收集结构化结果来评测 agent。本页详细说明该流水线的工作原理——从 YAML 到 `ResultMatrix`。

## 执行流水线概览

当你运行 `micro-eval run` 时，引擎按顺序执行以下阶段：

1. **解析与验证** — 加载 `eval.yaml`，应用 Pydantic schema 验证
2. **矩阵展开** — 将 `Tasks × Configurations × Repetitions` 分解为 `RunCell` 对象
3. **计划记录** — 在任何单元格执行之前，将 `RunPlan` 写入 `.micro-eval/runs/<run-id>/plan.json`
4. **有界并发执行** — 通过 asyncio 调度单元格，可配置并发上限
5. **单元格生命周期** — 准备工作区 → 运行 agent → 捕获输出 → 验证 → 评分 → 清理
6. **结果聚合** — 写入 `ResultMatrix`，计算决策，更新 SQLite 趋势索引

## 矩阵展开

`RunPlan` 是每个任务、每个配置和每个重复索引的笛卡尔积：

```
RunCells = Tasks × Configurations × range(repetitions)
```

例如，三个任务、两个配置和两次重复产生 **12 个单元格**：

```yaml{4,8,11}
tasks:
  - id: refactor
  - id: add-tests
  - id: fix-bug

configurations:
  - id: sonnet-skill-v1
  - id: sonnet-skill-v2

# repetitions is set per configuration:
# configurations[].repetitions: 2
```

每个单元格携带一个稳定的标识——`(task_id, config_id, rep_index)`——在执行开始前记录在 `plan.json` 中。这意味着中断运行的部分结果始终可追溯。

## 执行顺序

默认情况下，单元格按**确定性顺序**执行：任务按声明顺序迭代，然后是配置，再是重复次数。这使得连续运行可以直接对比。

当你需要消除排序效应时——例如，怀疑顺序写入工作区会影响后续单元格——可启用随机化：

```yaml{2}
guardrails:
  randomize_execution_order: true
  # execution_seed is auto-generated and recorded in plan.json
```

生成的 `execution_seed` 始终写入 `plan.json` 并嵌入 `RunResult.metadata`，因此可以精确回放执行顺序。

## 并发控制

单元格通过 `asyncio` 并发运行，使用有界信号量：

```yaml
guardrails:
  max_concurrency: 4    # default; adjust based on available CPU/memory
```

::: tip 调优 `max_concurrency`
对于 CPU 密集型 agent 工作负载，将 `max_concurrency` 设置为可用核心数。对于 API 密集型 agent（LLM 调用），较高的值（8–16）是安全的。注意内存——每个单元格可能克隆一个 git worktree 并生成一个子进程。
:::

信号量确保最多 `max_concurrency` 个单元格同时处于子进程阶段。工作区准备和清理在信号量之外进行，以避免阻塞其他单元格。

## 单元格生命周期

每个 `RunCell` 经历相同的八步生命周期。任意步骤的失败都会产生一个结构化的 `CellError`，并跳过该单元格的后续步骤——但不影响其他单元格。

### 第 1 步 — 工作区准备

引擎根据 `workspace.type` 为每个单元格提供一个隔离的工作区：

| 类型 | 发生的操作 |
|---|---|
| `blank` | 创建一个空临时目录 |
| `files` | 将声明的文件复制到临时目录 |
| `git_repo` | 从指定仓库和提交创建一个 `git worktree` |

```yaml
workspace:
  type: git_repo
  path: .
  ref: HEAD           # pinned for reproducibility
  setup:
    - ["uv", "sync"]
```

每个单元格的 worktree 路径是唯一的——并行单元格永远不会共享文件系统根目录。

### 第 2 步 — 设置命令

`setup` 命令在 agent 被调用之前，在工作区内顺序运行。每条命令必须是 **argv 列表**（不使用 shell 字符串）：

```yaml{3,4,5}
workspace:
  setup:
    - ["uv", "sync", "--frozen"]
    - ["npm", "ci"]
    - ["python", "scripts/seed_db.py"]
```

如果任何设置命令以非零退出码退出，单元格立即转换为 `error` 状态，并标记 `phase: setup`。agent 不会被调用。

### 第 3 步 — Agent 子进程调用

agent 通过 Python 的 `asyncio.create_subprocess_exec` 启动——**绝不**使用 `shell=True`。完整命令构造为 argv 列表：

```yaml
configurations:
  - id: my-agent
    agent:
      command: ["uv", "run", "my-agent"]
      args: ["--task-file", "{task_file}"]   # placeholder expanded safely
      timeout: 120
```

任务提示通过临时文件或 stdin 传递——绝不插值到 shell 字符串中。这消除了整类注入漏洞。

::: warning 仅限 argv 的安全性
micro-eval 拒绝执行以 shell 字符串形式传递的 agent 命令。如果你的 `command` 值是包含空格或 shell 元字符的单个字符串，CLI 将在验证时拒绝该配置并给出明确的错误提示。始终使用列表：`["my-agent", "--flag", "value"]`。
:::

### 第 4 步 — 输出捕获

stdout、stderr 和声明的 artifact 路径在大小上限内捕获，以防止失控输出耗尽磁盘：

```yaml
guardrails:
  output_cap_bytes: 10485760    # 10 MB per cell (default)
  artifact_cap_bytes: 52428800  # 50 MB per artifact (default)
```

当某个流超过其上限时，捕获停止，并在 `CellResult` 上设置 `stdout_truncated: true`（或 `stderr_truncated: true`）。agent 进程不会被终止——只有捕获缓冲区会受到限制。

::: warning 输出截断会影响验证
如果 `stdout_truncated` 为 `true`，针对 stdout 末尾匹配的 `contains` 期望可能产生假阴性。调试意外的验证失败时请检查 `cell_result.stdout_truncated`。如果你的 agent 产生大量结构化输出，请在 `guardrails` 中增大 `output_cap_bytes`。
:::

### 第 5 步 — 确定性验证

期望按声明顺序对捕获的输出进行评估。micro-eval 支持四种期望类型：

::: code-group

```yaml [exit_code]
expectations:
  - type: exit_code
    value: 0
```

```yaml [contains]
expectations:
  - type: contains
    stream: stdout
    value: "refactoring complete"
    case_sensitive: false
```

```yaml [file_exists]
expectations:
  - type: file_exists
    path: "output/report.md"
    min_bytes: 100
```

```yaml [command]
expectations:
  - type: command
    command: ["python", "-m", "pytest", "tests/", "-q"]
    cwd: "{output_dir}"
```

:::

即使早期期望失败，所有期望仍会被评估——你将获得每个单元格的完整结果，而不仅仅是第一个失败。

### 第 6 步 — Trace 捕获（可选）

如果配置了 Langfuse 凭证，引擎会将 trace 元数据附加到 `CellResult`：

```bash
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...   # stored as LANGFUSE_SECRET_KEY in practice
export LANGFUSE_HOST=https://cloud.langfuse.com
```

Trace 捕获是尽力而为的——如果 Langfuse 端点不可达，单元格结果仍会写入，但不包含 trace 数据。

### 第 7 步 — 可选 LLM 评判

在确定性验证之后，可选的 LLM 评判根据评分标准对单元格进行评分：

```yaml
scoring:
  judge: gpt-4o
  rubric: |
    Score the agent's output on correctness (0-10) and clarity (0-10).
    Return JSON: {"correctness": <int>, "clarity": <int>}
  dimensions: [correctness, clarity]
```

LLM 评判失败（API 错误、JSON 响应格式错误）会在 `CellResult` 上产生 `judge_error` 字段，不影响确定性验证结果。

### 第 8 步 — 工作区清理

输出捕获和评分完成后，工作区被移除：

- `blank` / `files` 工作区：临时目录被删除
- `git_repo` 工作区：调用 `git worktree remove --force <path>`

即使 agent 以错误退出，清理也会运行。在 `run.preserve_artifacts` 下声明的 artifact 会在工作区移除之前复制到 `.micro-eval/runs/<run-id>/artifacts/`。

## 超时与信号升级

每个单元格都有可配置的超时。当 agent 超时时，引擎升级信号：

```
timeout exceeded
  → SIGTERM (graceful shutdown)
  → grace_window seconds (default: 10)
  → SIGKILL (forced)
```

按配置或全局配置：

```yaml{4,5}
configurations:
  - id: slow-agent
    agent:
      timeout: 300          # seconds; overrides run-level default
      grace_window: 15      # seconds between SIGTERM and SIGKILL
```

`CellResult` 记录 `exit_reason: timeout` 以及实际的挂钟时长。

## 单元格故障隔离

默认情况下，单元格错误（设置失败、agent 崩溃、超时）记录为状态为 `status: error` 的 `CellResult`，运行继续进行：

```yaml
guardrails:
  stop_on_cell_error: false   # default — continue on error
```

如果希望整个运行在第一次失败时停止，设置 `stop_on_cell_error: true`。这在初始配置阶段快速暴露问题时很有用。

::: tip 部分结果始终会被写入
即使运行被中断（Ctrl-C、OOM、网络断开），每个已完成单元格的结果在完成时都会被刷新到磁盘。中断之前已完成的单元格结果永远不会丢失。
:::

## 隔离级别

工作区 provider 决定单元格之间以及与宿主之间的隔离程度：

| 级别 | Provider | 保证 |
|---|---|---|
| `logical` | git worktree | 独立的文件系统树；共享宿主 OS 资源 |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | OS 强制执行的系统调用/文件系统策略 |
| `container` | Docker（计划中） | 完整容器命名空间隔离 |
| `vm` | E2B / Modal | 远程临时虚拟机；最强隔离 |

```yaml{2}
workspace:
  isolation_level: os_policy    # falls back to logical with a caveat if unavailable
```

当请求 `os_policy` 但 Seatbelt/Bubblewrap 不可用时（例如，操作系统不匹配或缺少权限），micro-eval 降级为 `logical` 并在运行元数据中记录一条 `SandboxCaveat`。远程 provider（`E2B`、`Modal`）**永不降级**——如果凭证缺失，它们会直接失败。

## Guardrails 参考

所有安全限制位于 `guardrails` 下：

```yaml
guardrails:
  max_concurrency: 4
  output_cap_bytes: 10485760
  artifact_cap_bytes: 52428800
  randomize_execution_order: false
  stop_on_cell_error: false
```

## Secrets 处理

以 `MICRO_EVAL_SECRET_` 为前缀的环境变量会转发给 agent 子进程，但会从所有日志、trace 和存储的 `CellResult` 记录中**自动脱敏**：

```bash
export MICRO_EVAL_SECRET_OPENAI_API_KEY=sk-...
export MICRO_EVAL_SECRET_GITHUB_TOKEN=ghp_...
```

不要通过配置 YAML 中的 `args` 传递 secrets——这些值存储在 `plan.json` 中且不会被脱敏。

::: danger 永远不要将 secrets 写入 YAML
写入 `eval.yaml` 或 `configurations[].agent.args` 下任何字段的内容都会以明文形式出现在 `.micro-eval/runs/<run-id>/plan.json` 中。所有凭证请使用 `MICRO_EVAL_SECRET_*` 环境变量。
:::

## 下一步

了解了执行机制后，下一个主题将介绍 micro-eval 如何对结果进行评分和标注：

[评估 →](/zh/guide/evaluation)
