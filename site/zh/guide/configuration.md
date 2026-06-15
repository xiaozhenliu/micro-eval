# 配置

`eval.yaml` 是每个 micro-eval 实验的核心配置文件。它回答一个问题：**你究竟在比较什么，在什么条件下比较？** 所有内容——被测 agent、要运行的任务、隔离策略、评分规则——都在这里定义或引用相关文件。

## 完整示例

将此文件复制为起点，然后删除不需要的部分。

```yaml
# eval.yaml
project_name: my-agent-comparison
description: >
  Compare the refactored coding agent (v2) against the baseline (v1)
  on a suite of Python file-transformation tasks.

# ─── Configurations ─────────────────────────────────────────────────────────
# Each configuration is one "column" in the result matrix.
configurations:
  - id: baseline
    name: Agent v1 (baseline)
    role: baseline          # baseline | candidate
    repetitions: 3          # how many times each task is run

    agent:
      command: ["python", "-m", "myagent.cli", "--mode", "transform"]
      input_mode: stdin     # stdin | file
      output_mode: stdout   # stdout | file | directory
      timeout_s: 120
      env:
        LOG_LEVEL: warning
      required_secrets:
        - MICRO_EVAL_SECRET_OPENAI_KEY

    skills_profile: null    # path to a skills YAML, or null

    parameters:             # arbitrary key-value passed as --param k=v
      model: gpt-4o-mini
      temperature: "0.0"

  - id: candidate
    name: Agent v2 (candidate)
    role: candidate
    repetitions: 3

    agent:
      command: ["python", "-m", "myagent_v2.cli", "--mode", "transform"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 120
      env:
        LOG_LEVEL: warning
      required_secrets:
        - MICRO_EVAL_SECRET_OPENAI_KEY

    skills_profile: skills/coding-v2.yaml

    parameters:
      model: gpt-4o
      temperature: "0.0"

# ─── Tasks ───────────────────────────────────────────────────────────────────
# Paths to task YAML files (relative to this file).
tasks:
  - tasks/rename-function.yaml
  - tasks/add-docstring.yaml
  - tasks/refactor-class.yaml

# ─── Guardrails ──────────────────────────────────────────────────────────────
guardrails:
  max_concurrency: 4          # parallel cells (default: 4)
  timeout_s: 300              # per-cell wall-clock timeout
  output_cap_bytes: 10485760  # 10 MB stdout cap
  artifact_cap_bytes: 52428800  # 50 MB artifact cap
  stop_on_cell_error: false   # abort entire run on first failure
  randomize_execution_order: false

# ─── Evaluation ──────────────────────────────────────────────────────────────
evaluation:
  comparison_subject: score   # what to compare across configurations
  min_repetitions: 2          # minimum reps needed to compute a decision
  required_evaluators:        # which evaluators must have run
    - validator
  denominator_policy: exclude_failed  # include_failed | exclude_failed
  decision_threshold: 0.10    # delta below which result is "inconclusive"
  inconclusive_policy: needs_human_review

# ─── Trace ───────────────────────────────────────────────────────────────────
trace:
  enabled: false
  provider: process           # process | langfuse

# ─── LLM Judge ───────────────────────────────────────────────────────────────
judge:
  enabled: false
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

::: tip 运行前先验证
编辑 `eval.yaml` 后，运行 `micro-eval validate` 来检查 schema 错误、缺失的任务文件以及未引用的 secret，避免浪费计算资源在完整 run 上。
:::

---

## 字段说明

### `project_name` 和 `description`

```yaml
project_name: my-agent-comparison
description: >
  A multiline description of what this experiment is testing.
```

`project_name` 会显示在报告和 Web UI 的 run 列表中。它不需要在所有 run 中唯一——micro-eval 使用自动生成的 run ID 来区分不同 run。

---

### `configurations[]`

每个条目对应结果矩阵中的一列。至少需要一个 configuration；若要进行比较决策，则需要两个或以上。

#### `id` 和 `name`

```yaml{2-3}
configurations:
  - id: baseline          # used in the result matrix and file paths
    name: Agent v1 (baseline)  # human-readable label in reports and UI
```

`id` 在文件中必须唯一，且只能包含字母、数字、连字符和下划线。

#### `role`

```yaml{2}
configurations:
  - role: baseline    # baseline | candidate
```

| 值 | 含义 |
|---|---|
| `baseline` | 参照基准。`improved`/`regressed` 等决策均相对于此。 |
| `candidate` | 被测变体。 |

如果只有一个 configuration，`role` 是可选的。如果存在两个或以上且没有标记 `baseline`，micro-eval 将第一个视为 baseline。

#### `repetitions`

```yaml{2}
configurations:
  - repetitions: 3
```

每个任务在此 configuration 下执行的次数。结果矩阵会对多次重复取聚合（均值分数、pass rate、p-value）。对于确定性任务设为 `1`；对于受方差影响的 LLM 驱动 agent，设为 `3–5`。

#### `agent`

**AgentSpec** 是一个 agent 的完整调用契约。它告诉 micro-eval 命令 argv、输入如何传递给 agent、输出如何收集、每次调用的超时时间、额外的环境变量，以及需要哪些 secrets。每个 configuration 在 `agent` 键下包含恰好一个 AgentSpec。

```yaml
agent:
  command: ["python", "-m", "myagent.cli", "--mode", "transform"]
  input_mode: stdin
  output_mode: stdout
  timeout_s: 120
  env:
    LOG_LEVEL: warning
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

::: warning command 必须是 argv 列表，而非 shell 字符串
`command` 必须是 YAML 列表——每个参数单独一个元素。不要这样写：

```yaml
# 错误 — 存在 shell 注入风险，无法按预期工作
command: "python -m myagent.cli --mode transform"
```

应写成列表形式：

```yaml
# 正确
command: ["python", "-m", "myagent.cli", "--mode", "transform"]
```

micro-eval 将列表直接传给 `asyncio.create_subprocess_exec`，完全绕过 shell。这可以防止 shell 注入，并确保参数边界精确无误。
:::

**`input_mode`**

| 值 | 行为 |
|---|---|
| `stdin` | 任务 prompt 写入 agent 的标准输入。 |
| `file` | 任务 prompt 写入临时文件，其路径作为最后一个 argv 元素追加。 |

**`output_mode`**

| 值 | 行为 |
|---|---|
| `stdout` | 从标准输出捕获 agent 输出。 |
| `file` | Agent 写入其接收到的路径，micro-eval 在退出后读取该路径。 |
| `directory` | Agent 向目录写入一个或多个文件，micro-eval 将它们全部收集为 artifact。 |

**`timeout_s`**

每次调用的挂钟超时时间（秒）。超时后该 cell 被标记为 `timeout`。此值还受 `guardrails.timeout_s` 约束——取两者中的较小值。

**`env`**

合并到子进程环境中的键值对，为明文值。密钥请使用 `required_secrets`。

**`required_secrets`**

```yaml
required_secrets:
  - MICRO_EVAL_SECRET_OPENAI_KEY
  - MICRO_EVAL_SECRET_ANTHROPIC_KEY
```

运行时必须存在并将转发给子进程的环境变量名称。micro-eval 在启动任何 cell 之前会验证它们是否存在，并从日志和存储的 trace 中对其值进行脱敏处理。Secret 变量必须遵循 `MICRO_EVAL_SECRET_*` 命名规范，或在此处明确列出，以便脱敏器知道需要处理它们。

#### `skills_profile`

```yaml
skills_profile: skills/coding-v2.yaml  # or null
```

挂载到 agent workspace 的 skills YAML 文件路径。当 agent 不使用 skills profile 时设为 `null`。路径相对于 `eval.yaml` 解析。

#### `parameters`

```yaml
parameters:
  model: gpt-4o
  temperature: "0.0"
  max_tokens: "4096"
```

以 `--param key=value` argv 元素形式追加在 `command` 之后传给 agent 的任意字符串键值对。所有值必须为字符串（数字需加引号）。parameters 会显示在结果矩阵的列标题中，并与每次 run 一起存储以确保可复现性。

---

### `tasks[]`

```yaml
tasks:
  - tasks/rename-function.yaml
  - tasks/add-docstring.yaml
```

任务 YAML 文件的路径列表，相对于 `eval.yaml` 解析。每个任务对应结果矩阵中的一行。任务文件格式请参阅 [Tasks](/zh/guide/tasks) 指南。

---

### `guardrails`

Guardrails 限制资源使用，并在 run 级别控制执行行为。

```yaml
guardrails:
  max_concurrency: 4
  timeout_s: 300
  output_cap_bytes: 10485760
  artifact_cap_bytes: 52428800
  stop_on_cell_error: false
  randomize_execution_order: false
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `max_concurrency` | `4` | 并行执行的最大 cell 数（task × configuration × repetition）。 |
| `timeout_s` | `300` | 每个 cell 的挂钟超时时间（秒）。覆盖 agent `timeout_s` 中的较大值。 |
| `output_cap_bytes` | `10485760` | 每个 cell 从 stdout/stderr 捕获的最大字节数（10 MB）。超出部分被截断。 |
| `artifact_cap_bytes` | `52428800` | 每个 cell 存储的 artifact 总字节数上限（50 MB）。 |
| `stop_on_cell_error` | `false` | 若为 `true`，任何 cell 以错误退出时立即中止整个 run。 |
| `randomize_execution_order` | `false` | 打乱 cell 执行顺序以减少系统性排序偏差。 |

::: tip 调整并发数
`max_concurrency` 控制跨所有 configuration 和 repetition 同时运行的 agent 子进程数量。当 agent 调用有速率限制的外部 API 时，或当你需要测量延迟并希望避免竞争时，请从较低值（2–4）开始。
:::

---

### `evaluation`

控制每个 cell 的分数如何聚合为每个任务行的决策。

```yaml
evaluation:
  comparison_subject: score
  min_repetitions: 2
  required_evaluators:
    - validator
  denominator_policy: exclude_failed
  decision_threshold: 0.10
  inconclusive_policy: needs_human_review
```

| 字段 | 默认值 | 说明 |
|---|---|---|
| `comparison_subject` | `score` | 跨 configuration 比较的指标。 |
| `min_repetitions` | `1` | 计算决策所需的最少完成重复次数。完成数不足的行被标记为 `not_comparable`。 |
| `required_evaluators` | `["validator"]` | cell 纳入聚合必须产生结果的 evaluator ID。 |
| `denominator_policy` | `exclude_failed` | 计算 pass rate 时，失败 cell 是否计入分母。 |
| `decision_threshold` | `0.05` | baseline 与 candidate 之间产生非 `inconclusive` 决策所需的最小分数差值。 |
| `inconclusive_policy` | `needs_human_review` | 差值低于 `decision_threshold` 时分配的决策状态。 |

**`denominator_policy`**

::: code-group

```yaml [exclude_failed]
# Only completed cells count toward the denominator.
# Use when failures are expected and you want to compare quality among successful runs.
denominator_policy: exclude_failed
```

```yaml [include_failed]
# All cells (including timeouts and errors) count toward the denominator.
# Use when failure rate itself is part of what you are measuring.
denominator_policy: include_failed
```

:::

**决策状态**

| 状态 | 含义 |
|---|---|
| `improved` | candidate 分数显著高于 baseline。 |
| `regressed` | candidate 分数显著低于 baseline。 |
| `mixed` | 不同任务呈现相反方向。 |
| `inconclusive` | 差值在 `decision_threshold` 范围内。 |
| `not_comparable` | 数据不足（重复次数太少、缺少 evaluator）。 |
| `needs_human_review` | 路由至人工标注员（见 `inconclusive_policy`）。 |

---

### `trace`

```yaml
trace:
  enabled: false
  provider: process   # process | langfuse
```

当 `enabled: true` 且 `provider: process` 时，micro-eval 使用自带的轻量级 tracer 从子进程捕获计时和 token 用量数据。切换到 `provider: langfuse` 可将 span 转发到运行中的 Langfuse 实例——在环境中设置 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` 和 `LANGFUSE_HOST`。Tracing 始终是可选的；若 provider 不可用，run 照常进行。

---

### `judge`

```yaml
judge:
  enabled: false
  provider: deepeval
  model: gpt-4o
  temperature: 0.0
  pass_threshold: 0.7
  required_secrets:
    - MICRO_EVAL_SECRET_OPENAI_KEY
```

LLM judge 在确定性 validator 之后运行，产生 0 到 1 之间的连续分数。它是可选的——当确定性预期已足够，或希望在初始迭代阶段控制成本时，可以禁用它。

| 字段 | 说明 |
|---|---|
| `provider` | 评分后端。目前为 `deepeval`。 |
| `model` | 传给 provider 用于评判的 model ID。 |
| `temperature` | judge model 的采样温度。`0.0` 可得到确定性判断。 |
| `pass_threshold` | cell 被视为"通过"并纳入聚合的最低分数。 |
| `required_secrets` | 转发给 judge provider（而非 agent）的 secret。 |

::: warning Judge 成本与 agent 成本独立计算
judge model 会发起自己的 API 调用。在任务数量多、重复次数多的情况下，judge 成本可能超过 agent 成本。请合理预算，或设置 `judge.enabled: false` 并依赖 `required_evaluators: [validator]`，直到确实需要基于 LLM 的评分。
:::

---

## 配置查找顺序

micro-eval 按以下优先级解析 `eval.yaml`（第一个匹配项优先）：

1. **`--config <path>`** 传给 `micro-eval run` 或 `micro-eval validate` 的标志
2. **`$MICRO_EVAL_CONFIG`** 环境变量
3. 当前工作目录中的 **`./eval.yaml`**

::: code-group

```bash [flag]
micro-eval run --config experiments/my-experiment.yaml
```

```bash [env var]
export MICRO_EVAL_CONFIG=experiments/my-experiment.yaml
micro-eval run
```

```bash [default]
# eval.yaml in current directory is used automatically
micro-eval run
```

:::

---

## 最简配置

并非每个部分都是必填的。以下是最小有效 `eval.yaml`：

```yaml
project_name: hello-eval

configurations:
  - id: my-agent
    agent:
      command: ["python", "agent.py"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 60

tasks:
  - tasks/hello.yaml
```

省略的部分使用默认值：重复 1 次、max_concurrency 4、无 judge、无 trace、exclude_failed 分母策略。

---

## 下一步

- [Tasks](/zh/guide/tasks) — 定义结果矩阵的行：prompt、workspace 和预期结果。
