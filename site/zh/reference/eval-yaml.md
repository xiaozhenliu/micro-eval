# eval.yaml Schema 参考

每个 micro-eval 项目都由一个 `eval.yaml` 文件驱动。该文件声明评测对象（任务）、评测方式（配置）以及结果可信的条件（守护规则、评测契约）。

::: tip 文件位置
按惯例，`eval.yaml` 位于项目根目录，与 tasks 目录并列。运行 `micro-eval init` 可生成带注释的起始文件。
:::

## 最小示例

```yaml
project_name: my-agent-eval
description: Compare v1 vs v2 of my coding agent

configurations:
  - id: v1-baseline
    name: "Agent v1 (baseline)"
    role: baseline
    agent:
      command: ["python", "agent_v1.py"]

  - id: v2-candidate
    name: "Agent v2 (candidate)"
    role: candidate
    agent:
      command: ["python", "agent_v2.py"]

tasks_dir: tasks
```

## 完整注释示例

```yaml
project_name: coding-agent-eval
description: "Phase 3 evaluation: tool-use improvements"

configurations:
  - id: gpt4o-baseline
    name: "GPT-4o (baseline)"
    role: baseline
    repetitions: 3
    agent:
      name: coding-agent
      command: ["uv", "run", "agent.py", "--model", "gpt-4o"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 120.0
      env:
        LOG_LEVEL: "info"
      required_secrets:
        - MICRO_EVAL_SECRET_OPENAI_KEY
    parameters:
      temperature: 0.0

  - id: sonnet-candidate
    name: "Claude Sonnet (candidate)"
    role: candidate
    repetitions: 3
    agent:
      name: coding-agent
      command: ["uv", "run", "agent.py", "--model", "claude-sonnet-4-5"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 120.0
      required_secrets:
        - MICRO_EVAL_SECRET_ANTHROPIC_KEY

tasks_dir: tasks
output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 4
  timeout_s: 300.0
  output_cap_bytes: 10485760
  artifact_cap_bytes: 52428800
  stop_on_cell_error: false
  randomize_execution_order: false

evaluation:
  comparison_subject: "tool-use accuracy on file tasks"
  task_set_version: "v1.2"
  success_criteria:
    - "exit code 0 on all tasks"
    - "no regressions vs baseline"
  decision_threshold: 0.05
  inconclusive_policy: warn
  min_repetitions: 3
  required_evaluators:
    - validator
    - judge
  denominator_policy: include_failed

trace:
  enabled: true
  provider: langfuse

judge:
  enabled: true
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

---

## 顶层字段

| 字段 | 类型 | 默认值 | 是否必填 | 描述 |
|---|---|---|---|---|
| `project_name` | `string` | `"unnamed"` | 否 | 人类可读的项目标签，显示在报告和 UI 中。 |
| `description` | `string` | `""` | 否 | 显示在运行摘要和报告头部的自由文本描述。 |
| `configurations` | `ConfigurationSpec[]` | — | **是** | 一个或多个待评测的 agent 配置，至少需要一条。 |
| `tasks` | `string[]` | `[]` | 否 | 显式指定的 task YAML 文件路径列表。当与 `tasks_dir` 同时设置时优先生效。 |
| `tasks_dir` | `string` | `"tasks"` | 否 | 扫描 `*.yaml` task 文件的目录。当 `tasks` 非空时忽略此字段。 |
| `output_dir` | `string` | `".micro-eval/runs"` | 否 | 运行结果的写入目录。必须是不含 `..` 段的相对路径。 |
| `guardrails` | [`Guardrails`](#guardrails) | *(见下文)* | 否 | 应用于运行矩阵中每个 cell 的资源与安全限制。 |
| `evaluation` | [`EvaluationContract`](#evaluationcontract) | *(见下文)* | 否 | 结果比较方式及决策判定条件。 |
| `trace` | [`TraceConfig`](#traceconfig) | *(见下文)* | 否 | 用于捕获执行 trace 的可观测性设置。 |
| `judge` | [`JudgeConfig`](#judgeconfig) | *(见下文)* | 否 | 用于自动评分的 LLM-as-judge 配置。 |

---

## ConfigurationSpec

一个 configuration 对应结果矩阵中的一列——它完整指定了 agent 程序、参数，以及每个任务需要重复执行的次数。

```yaml{4,9-11}
configurations:
  - id: my-agent-v2          # 必填，路径安全的标识符
    name: "My Agent v2"      # 必填，显示名称
    role: candidate          # baseline 或 candidate
    repetitions: 3           # 每个 task 运行 3 次
    agent:
      command: ["python", "agent.py"]
    parameters:
      temperature: 0.2       # 通过环境变量或 stdin 元数据传递给 agent
      max_tokens: 1024
```

| 字段 | 类型 | 默认值 | 是否必填 | 描述 |
|---|---|---|---|---|
| `id` | `string` | — | **是** | 该 configuration 的唯一标识符。允许字符：`A-Z a-z 0-9 _ . : -`。用于文件路径和报告键名。 |
| `name` | `string` | — | **是** | 显示在 UI 和报告中的名称。 |
| `role` | `string \| null` | `null` | 否 | 将此 configuration 声明为 `baseline` 或 `candidate`。决策逻辑用于计算回退/改进。 |
| `repetitions` | `integer` | `1` | 否 | 该 configuration 下每个 task 的执行次数，最小值为 `1`。较高的值可降低方差。 |
| `agent` | [`AgentSpec`](#agentspec) | — | **是** | agent 程序规格。 |
| `skills_profile` | `dict` | `{}` | 否 | 描述该 configuration 挂载了哪些 skill 或能力的键值对。仅作参考，存储在元数据中。 |
| `parameters` | `dict` | `{}` | 否 | 该 configuration 的任意键值参数。存储在运行元数据中；agent 通过 stdin task 元数据或环境变量接收。 |

### AgentSpec

定义 agent 可执行文件以及 micro-eval 与其通信的方式。

::: warning 仅支持 argv 执行
`command` 始终以 argv 列表的形式传递给 `subprocess`，绝不会插值到 shell 字符串中。不要在 `command` 中使用 shell 特性（管道、重定向、通配符）。这是安全要求，不是便利性限制。
:::

```yaml
agent:
  name: my-agent
  command: ["uv", "run", "src/agent.py", "--json-output"]
  input_mode: stdin          # 或：file
  output_mode: stdout        # 或：file、directory
  timeout_s: 120.0
  env:
    LOG_LEVEL: debug
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

| 字段 | 类型 | 默认值 | 是否必填 | 描述 |
|---|---|---|---|---|
| `name` | `string` | — | 否 | 人类可读的 agent 名称，用于展示。 |
| `command` | `string[]` | — | **是** | 启动 agent 的 argv 列表，不能为空。第一个元素必须是可执行文件。 |
| `input_mode` | `"stdin" \| "file"` | `"stdin"` | 否 | task prompt 的传递方式。`stdin`：写入进程标准输入。`file`：写入临时文件，文件路径作为最后一个 argv 元素传入。 |
| `output_mode` | `"stdout" \| "file" \| "directory"` | `"stdout"` | 否 | agent 写入结果的位置。`stdout`：从标准输出捕获。`file`：agent 写入已知文件路径。`directory`：agent 将多个 artifact 写入某目录。 |
| `timeout_s` | `float` | `300.0` | 否 | 每个 cell 的执行超时时间（秒），必须大于 `0`。设置后会覆盖 `guardrails.timeout_s`。 |
| `env` | `dict` | `{}` | 否 | 注入 agent 子进程的额外环境变量，值必须为字符串。不要在此处放置 secret——请使用 `required_secrets`。 |
| `required_secrets` | `string[]` | `[]` | 否 | agent 所需的 secret 名称列表。每个名称必须以 `MICRO_EVAL_SECRET_` 开头。micro-eval 从宿主环境读取并注入子进程，绝不记录或存储到输出文件中。 |

#### input_mode 详解

::: code-group

```yaml [stdin（默认）]
agent:
  command: ["python", "agent.py"]
  input_mode: stdin
# Task prompt 以纯文本形式写入 agent 的标准输入。
# Agent 读取 sys.stdin 并将结果写入 stdout。
```

```yaml [file]
agent:
  command: ["python", "agent.py"]
  input_mode: file
# Task prompt 写入临时文件。
# 文件路径作为最后一个 argv 元素追加。
# 例如：python agent.py /tmp/micro-eval-task-abc123.txt
```

:::

#### output_mode 详解

::: code-group

```yaml [stdout（默认）]
agent:
  output_mode: stdout
# Agent 结果从 stdout 捕获。
# Stderr 单独捕获用于诊断，不参与评分。
```

```yaml [file]
agent:
  output_mode: file
# Agent 将输出写入通过
# MICRO_EVAL_OUTPUT_FILE 环境变量提供的文件路径。
```

```yaml [directory]
agent:
  output_mode: directory
# Agent 将多个 artifact 写入
# MICRO_EVAL_OUTPUT_DIR 指向的目录，所有文件均被收集为 artifact。
```

:::

---

## Guardrails

Guardrails 限制 `Tasks × Configurations × Repetitions` 矩阵中每个 cell 的资源使用，并控制执行安全性。

```yaml
guardrails:
  max_concurrency: 4
  timeout_s: 300.0
  output_cap_bytes: 10485760    # 10 MB
  artifact_cap_bytes: 52428800  # 50 MB
  stop_on_cell_error: false
  randomize_execution_order: false
```

| 字段 | 类型 | 默认值 | 是否必填 | 描述 |
|---|---|---|---|---|
| `max_concurrency` | `integer` | `4` | 否 | 并行执行的最大 cell 数，最小值为 `1`。控制 asyncio 有界并发。 |
| `timeout_s` | `float` | `300.0` | 否 | 默认每 cell 超时时间（秒）。可通过 `agent.timeout_s` 按 agent 覆盖。 |
| `output_cap_bytes` | `integer` | `10485760` | 否 | 每 cell 从 stdout/stderr 捕获的最大字节数（10 MB），超出部分将被截断。 |
| `artifact_cap_bytes` | `integer` | `52428800` | 否 | 每 cell 收集的文件 artifact 总字节数上限（50 MB）。 |
| `stop_on_cell_error` | `boolean` | `false` | 否 | 为 `true` 时，cell 失败（非零退出、超时、报错）将立即中止整个运行。默认 `false` 会收集所有结果后再报告。 |
| `randomize_execution_order` | `boolean` | `false` | 否 | 为 `true` 时，cell 以随机顺序执行。适用于检测顺序相关的不稳定性。 |

::: tip 调整并发数
对于本地 agent，将 `max_concurrency` 设置为可用 CPU 核心数；若 agent 频繁调用外部 API 且需要避免限速，可适当降低该值。
:::

---

## EvaluationContract

评测契约声明运行产出可信决策的条件，在所有 cell 完成后进行检查。

```yaml{6-8}
evaluation:
  comparison_subject: "file editing accuracy"
  task_set_version: "v2.0"
  success_criteria:
    - "exit code 0 on all tasks"
    - "no regressions vs baseline"
  decision_threshold: 0.05
  inconclusive_policy: warn
  min_repetitions: 3
  required_evaluators:
    - validator
    - judge
  denominator_policy: include_failed
```

| 字段 | 类型 | 默认值 | 是否必填 | 描述 |
|---|---|---|---|---|
| `comparison_subject` | `string \| null` | `null` | 否 | 比较对象的人类可读描述，显示在报告中。 |
| `task_set_version` | `string` | — | 否 | task 集合的版本标签。存储在运行元数据中，用于趋势分析中检测不可比的运行。 |
| `success_criteria` | `string[]` | `[]` | 否 | 人类可读的成功评测标准，作为文档存储在运行记录中。 |
| `budget` | `dict \| null` | `null` | 否 | 可选的成本预算约束，键名和 schema 取决于 trace provider。 |
| `decision_threshold` | `float \| null` | `null` | 否 | 声明结果为 `improved` 或 `regressed` 所需的最小分数差值，低于该阈值则判定为 `inconclusive`。 |
| `inconclusive_policy` | `"warn" \| "block"` | `"warn"` | 否 | 决策为 `inconclusive` 时的处理方式。`warn` 发出警告并继续；`block` 以非零状态码退出。 |
| `min_repetitions` | `integer` | `1` | 否 | cell 纳入决策所需的最小重复次数，成功重复次数不足的 cell 将被排除。 |
| `required_evaluators` | `string[]` | `["validator"]` | 否 | cell 被计入结果所需的评估器列表，支持的值：`validator`、`judge`。 |
| `denominator_policy` | `"include_failed" \| "exclude_failed"` | `"include_failed"` | 否 | 计算通过率时失败的 cell（超时、报错）是否计入分母。`include_failed` 更为保守。 |

### 决策状态

运行完成后，micro-eval 会计算出以下决策状态之一：

| 状态 | 含义 |
|---|---|
| `improved` | candidate 显著优于 baseline（delta ≥ 阈值）。 |
| `regressed` | candidate 显著弱于 baseline（delta ≤ −阈值）。 |
| `mixed` | 部分 task 改善，部分回退，没有明确胜者。 |
| `inconclusive` | delta 在阈值范围内，需要更多数据。 |
| `not_comparable` | 运行条件不同（task 集版本、workspace 等不一致）。 |
| `needs_human_review` | 自动评分不足，需要人工标注。 |

---

## TraceConfig

控制用于可观测性的执行 trace。使用 `provider: langfuse` 时，请将 Langfuse 凭证配置为 `MICRO_EVAL_SECRET_*` 环境变量。

```yaml
trace:
  enabled: true
  provider: langfuse   # 或：process
```

| 字段 | 类型 | 默认值 | 是否必填 | 描述 |
|---|---|---|---|---|
| `enabled` | `boolean` | `false` | 否 | 启用 trace 收集。为 `false` 时不输出任何 trace 数据。 |
| `provider` | `"process" \| "langfuse"` | `"process"` | 否 | trace 后端。`process`：在本地捕获时序和 I/O 数据。`langfuse`：将 trace 流式传输到 Langfuse 实例（需要 `LANGFUSE_*` 环境变量）。 |

::: tip Langfuse 凭证
在运行前于 shell 环境中设置以下变量：
```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://cloud.langfuse.com
```
micro-eval 会自动读取并注入，绝不会写入输出文件。
:::

---

## JudgeConfig

配置用于自动评分的 LLM-as-judge。judge 在确定性验证器之后运行，为每个 cell 生成 0 到 1 之间的 `pass_score`。

::: warning Judge 为可选功能
judge 会增加延迟和成本。仅在确定性验证（`exit_code`、`contains`、`file_exists`、`command`）不足以满足 task 评分标准时才启用。
:::

```yaml
judge:
  enabled: true
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

| 字段 | 类型 | 默认值 | 是否必填 | 描述 |
|---|---|---|---|---|
| `enabled` | `boolean` | `false` | 否 | 启用 LLM judge。为 `false` 时仅运行确定性验证。 |
| `provider` | `"deepeval"` | `"deepeval"` | 否 | 使用的评分库，目前仅支持 `deepeval`。 |
| `model` | `string` | — | 否 | 传给 judge provider 的模型标识符（如 `"gpt-4o"`、`"claude-sonnet-4-5"`）。 |
| `temperature` | `float` | `0.0` | 否 | judge 模型的采样温度，推荐使用 `0.0` 以获得确定性评分。 |
| `pass_threshold` | `float` | `0.5` | 否 | judge 判定 cell 通过的最低分数（0–1），低于该阈值的 cell 计为 judge-fail。 |
| `required_secrets` | `string[]` | `[]` | 否 | judge 所需的 secret（如 judge 模型的 API key）。每个名称必须以 `MICRO_EVAL_SECRET_` 开头。 |

### 评测流水线

评测分三个阶段依次运行：

```
┌─────────────────────────────────────────┐
│  Stage 1: Deterministic Validator       │
│  exit_code · contains · file_exists     │
│  command                                │
│  → pass / fail (binary, fast, free)     │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Stage 2: LLM Judge (optional)          │
│  deepeval custom metric                 │
│  → pass_score ∈ [0, 1]                  │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Stage 3: Human Annotation (optional)   │
│  via Web UI annotation interface        │
│  → overrides or supplements judge score │
└─────────────────────────────────────────┘
```

---

## Workspace 类型

Workspace 配置位于各个 task 文件中，但隔离级别是 micro-eval 启动每个 cell 方式的属性。四种隔离级别如下：

| 级别 | 值 | 描述 |
|---|---|---|
| 逻辑隔离 | `logical` | 每个 cell 使用独立的 git worktree。速度快，无 OS 级隔离。默认值。 |
| OS 策略 | `os_policy` | Seatbelt（macOS）或 Bubblewrap（Linux）。不可用时降级为 `logical` 并附带警告。 |
| 容器 | `container` | OCI 容器（非本地 Docker），计划中。 |
| 虚拟机 / 远程 | `vm` | E2B 或 Modal 远程沙箱。需要凭证；未配置时直接报错（不会静默降级）。 |

三种 task workspace 类型如下：

| 类型 | 描述 |
|---|---|
| `blank` | 空目录，agent 启动时无任何文件。 |
| `files` | 执行前复制一组文件到 workspace。 |
| `git_repo` | 检出到指定 commit 的 git 仓库，支持多源 fixture 和 toolchain 指纹。 |

---

## Secret 处理

::: danger 禁止在 eval.yaml 中写入 secret
不要将 secret 值写入 `eval.yaml`，该文件会被纳入版本控制。使用 `required_secrets` 声明所需的 secret，并在运行前以环境变量的形式设置。
:::

所有 secret 环境变量必须使用 `MICRO_EVAL_SECRET_` 前缀：

```bash
# 在运行 micro-eval 前设置
export MICRO_EVAL_SECRET_OPENAI_KEY=sk-...
export MICRO_EVAL_SECRET_ANTHROPIC_KEY=sk-ant-...
export LANGFUSE_SECRET_KEY=sk-lf-...
```

micro-eval 的处理流程：
1. 启动时从宿主环境读取已声明的 secret。
2. 在启动任何 cell 之前验证所有 `required_secrets` 均已存在。
3. 直接注入子进程环境——从不通过 shell 插值传递。
4. 在写入磁盘前，自动从 stdout、stderr 及 artifact 捕获内容中脱敏所有 `MICRO_EVAL_SECRET_*` 的值。

---

## 验证

运行 `micro-eval validate` 可在启动运行前根据 Pydantic schema 检查 `eval.yaml`：

```bash
micro-eval validate
# 或指定特定文件：
micro-eval validate --config path/to/eval.yaml
```

常见验证错误：

| 错误 | 修复方法 |
|---|---|
| `configurations: field required` | 在 `configurations` 下添加至少一条配置。 |
| `id: string does not match pattern` | Configuration `id` 只能使用 `A-Za-z0-9_.:- ` 字符。 |
| `command: must be non-empty` | `agent.command` 必须是至少含一个元素的列表。 |
| `required_secrets: must use MICRO_EVAL_SECRET_* prefix` | 将 secret 名称改为以 `MICRO_EVAL_SECRET_` 开头。 |
| `output_dir: must be relative with no .. segments` | 将 `output_dir` 改为不含 `..` 的相对路径。 |
| `timeout_s: must be > 0` | 将 `timeout_s` 设置为正数。 |
