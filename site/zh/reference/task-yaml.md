# task.yaml Schema

**task** 是 micro-eval 中评测的原子单元。每个 task 描述一个 prompt、其预期输出，以及 agent 运行时所需的 workspace。task 以 YAML 文件形式存储，由引擎在运行时加载。

::: tip 快速开始
运行 `micro-eval init` 可在项目中生成一个初始 `task.yaml`，然后根据下方的字段参考进行扩展。
:::

## 文件结构概览

```yaml
# task.yaml
id: summarize-pr-diff
name: Summarize a pull-request diff
description: Agent must produce a concise summary of a git diff.

input_payload: |
  Summarize the following git diff in 3 bullet points.
  Focus on what changed and why it matters.
  {{diff}}

expected_output: "- "
rubric:
  text: Evaluate the summary for accuracy, brevity, and actionability.
  dimensions:
    - accuracy
    - brevity
    - { name: actionability, weight: 0.5 }

workspace:
  type: git_repo
  path: ./fixtures/sample-repo
  ref: HEAD
  isolation_level: logical

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "- "
    stream: output

business_impact_tier: 2
tags: [code-review, summarization]
revision_id: v1
```

---

## TaskSpec

`task.yaml` 文件的根对象。

| 字段 | 类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
| `id` | `string` | 是 | — | 唯一任务标识符，只允许使用 `A-Za-z0-9_.:‑` 字符，用于文件路径和结果键。 |
| `name` | `string` | 是 | — | 在 UI 和报告中显示的人类可读名称。 |
| `description` | `string` | 否 | `""` | 可选的详细描述，显示在 run 摘要中。 |
| `input_payload` | `string` | 是 | — | 通过 stdin 或文件传递给 agent 的 prompt 文本，支持在运行时解析的 `{{variable}}` 占位符。 |
| `expected_output` | `string \| null` | 否 | `null` | 用于确定性验证器和 LLM judge 评分上下文的参考字符串。 |
| `rubric` | `string \| RubricSpec \| null` | 否 | `null` | 评分标准。纯字符串形式等同于 `rubric.text`。 |
| `expectations` | `ExpectationSpec[]` | 否 | `[]` | agent 退出后依次执行的确定性检查列表，全部通过才将该 task 标记为 `passed`。 |
| `workspace` | `WorkspaceSpec` | 否 | `{type: blank}` | 描述 agent 执行时的文件系统环境和隔离策略。 |
| `business_impact_tier` | `int` | 否 | `3` | 优先级层级（`1` 为最高），用于在 ResultMatrix 中对聚合分数加权。 |
| `tags` | `string[]` | 否 | `[]` | 用于过滤 run 的任意标签（`micro-eval run --tag code-review`）。 |
| `revision_id` | `string` | 否 | `""` | 跟踪该 task 定义的版本，存储在 run 结果中用于可比性检查。 |

::: warning id 格式要求
`id` 字段必须是路径安全的，避免使用空格、斜杠和特殊字符。推荐使用 `kebab-case` 或 `snake_case`。引擎会使用该值构造输出路径，例如 `.micro-eval/runs/<run-id>/tasks/<task-id>/`。
:::

---

## ExpectationSpec

Expectations 是在 agent 子进程退出后执行的确定性检查，按顺序依次运行。

| 字段 | 类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
| `type` | `string` | 是 | — | `exit_code`、`contains`、`file_exists`、`command` 之一。 |
| `value` | `string \| int \| null` | 否 | `null` | 期望值。`exit_code` 类型为整数，`contains` 类型为子字符串。 |
| `path` | `string \| null` | 否 | `null` | 相对于 workspace 根目录的文件路径，供 `file_exists` 使用。 |
| `stream` | `string` | 否 | `"output"` | `contains` 检查的目标流，可选 `stdout`、`stderr`、`output`（stdout + stderr 合并）。 |
| `command` | `string[] \| null` | 否 | `null` | `command` 类型的 argv 数组，永远不要使用 shell 字符串，请以列表形式传入参数。 |
| `cwd` | `string \| null` | 否 | `null` | `command` 执行的工作目录，支持 `{output_dir}` 占位符。 |
| `timeout_s` | `float` | 否 | `30.0` | expectation 命令被终止前的超时秒数。 |

### Expectation 类型：`exit_code`

检查 agent 进程是否以指定退出码退出。

```yaml{3-4}
expectations:
  - type: exit_code
    value: 0          # pass if agent exits cleanly
```

```yaml
expectations:
  - type: exit_code
    value: 1          # expect intentional failure (e.g. a linting task)
```

### Expectation 类型：`contains`

检查 agent 输出中是否包含特定子字符串。

```yaml{3-5}
expectations:
  - type: contains
    value: "LGTM"
    stream: output    # stdout + stderr merged
```

```yaml
expectations:
  - type: contains
    value: "ERROR"
    stream: stderr    # only check stderr
```

::: tip 多个子字符串
添加多个 `contains` expectation 可以断言多个字符串同时存在，每项独立检查。
:::

### Expectation 类型：`file_exists`

检查 agent 是否在 workspace 内指定路径创建（或保留）了文件。

```yaml{3-4}
expectations:
  - type: file_exists
    path: output/report.md     # relative to workspace root
```

```yaml
expectations:
  - type: file_exists
    path: dist/bundle.js
  - type: file_exists
    path: dist/bundle.css
```

### Expectation 类型：`command`

运行任意命令并检查其退出码是否为 `0`，可用于测试运行器、linter 或自定义验证器。

```yaml{3-6}
expectations:
  - type: command
    command: [python, -m, pytest, tests/]
    cwd: "{output_dir}"        # run inside the agent's output directory
    timeout_s: 60.0
```

```yaml
expectations:
  - type: command
    command: [npx, tsc, --noEmit]
    cwd: "{output_dir}"
```

::: danger 永远不要在 command 中使用 shell 字符串
务必将 `command` 写成 YAML 字符串列表（argv）的形式。引擎会将这些参数直接传给子进程，不会进行 shell 插值。使用 shell 字符串会产生注入风险，并且在文件名包含空格时会出错。

```yaml
# 错误写法 — shell 字符串
command: "pytest tests/ && echo done"

# 正确写法 — argv 列表
command: [pytest, tests/]
```
:::

---

## WorkspaceSpec

描述 agent 启动时所看到的文件系统状态以及执行期间应用的隔离策略。

| 字段 | 类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
| `type` | `string` | 否 | `"blank"` | workspace 类型，可选 `blank`、`files`、`git_repo`。 |
| `path` | `string \| null` | 否 | `null` | 源仓库路径，`type: git_repo` 时必填。 |
| `ref` | `string \| null` | 否 | `null` | 要检出的 Git ref（branch、tag 或 SHA），默认为当前 HEAD。 |
| `files` | `string[]` | 否 | `[]` | 要复制到 workspace 中的文件或目录路径列表，与 `type: files` 配合使用。 |
| `setup` | `string[][]` | 否 | `[]` | 在 agent 启动**之前**在 workspace 内运行的 argv 命令列表，用于安装依赖或初始化数据。 |
| `isolation_level` | `string` | 否 | `"logical"` | 可选 `logical`、`os_policy`、`container`、`vm`。 |
| `trust_level` | `string` | 否 | `"trusted"` | 可选 `trusted`、`semi_trusted`、`untrusted`、`adversarial`，用于通知沙箱策略。 |
| `network_policy` | `string \| null` | 否 | `null` | 可选 `full`、`allowlist`、`none` 或 `null`（继承自 configuration）。 |
| `fixtures` | `FixtureSource[]` | 否 | `[]` | 注入 workspace 的额外文件，支持可选的 digest 校验。 |
| `toolchain` | `ToolchainSpec \| null` | 否 | `null` | 用于可比性跟踪的运行时和 lockfile 指纹。 |

### Workspace 类型：`blank`

一个空的临时目录，agent 启动时没有任何预置文件。

```yaml
workspace:
  type: blank
  isolation_level: logical
```

`blank` 适用于 agent 需要从零创建所有输出的 task，例如根据 prompt 生成文件。

### Workspace 类型：`files`

在 agent 运行前将一组文件或目录复制到 workspace 中。

```yaml{2-7}
workspace:
  type: files
  files:
    - ./fixtures/input.csv
    - ./fixtures/schema.json
  setup:
    - [pip, install, -r, requirements.txt]
  isolation_level: logical
```

::: tip 相对路径
`files` 中的路径相对于 `task.yaml` 文件所在位置解析，建议使用项目相对路径以保证可复现性。
:::

### Workspace 类型：`git_repo`

使用 git worktree 在指定 ref 上检出一个 git 仓库，推荐用于代码编辑和 agentic coding 类 task。

```yaml{2-6}
workspace:
  type: git_repo
  path: ./fixtures/sample-repo    # path to a git repo on disk
  ref: main                       # branch, tag, or full SHA
  isolation_level: logical        # git worktree per run
```

```yaml
# Pin to an exact commit for maximum reproducibility
workspace:
  type: git_repo
  path: /abs/path/to/repo
  ref: a3f9c12e
  isolation_level: os_policy
```

::: warning git_repo 需要 git 仓库
`path` 必须指向一个本身是 git 仓库的目录（包含 `.git` 目录）。引擎使用 `git worktree add` 为每次 run 创建独立的隔离副本。
:::

### 隔离级别

| 级别 | 后端 | 描述 |
|---|---|---|
| `logical` | git worktree | 每次 run 拥有独立的 worktree，速度快，无 OS 级沙箱。默认选项。 |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | OS 强制执行的系统调用和文件系统策略，不可用时降级为 `logical` 并附带 caveat。 |
| `container` | 预留 | 尚未实现。 |
| `vm` | E2B / Modal | 远程 VM 执行，需要 provider 凭证，未配置时直接失败，不会回退到其他级别。 |

::: code-group

```yaml [Development (logical)]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: logical
```

```yaml [CI (os_policy)]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
```

```yaml [Remote (vm)]
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: vm
  trust_level: untrusted
  network_policy: none
```

:::

### Setup 命令

Setup 命令在 agent 启动前于 workspace 内运行，以 argv 列表的列表形式传入，不要使用 shell 字符串。

```yaml{4-7}
workspace:
  type: git_repo
  path: ./fixtures/python-project
  setup:
    - [python, -m, pip, install, -r, requirements.txt]
    - [python, scripts/seed_db.py]
  isolation_level: logical
```

---

## FixtureSource

注入到 workspace 中的额外文件，与主 workspace 类型并存。支持 digest 校验，以便检测 run 间的 fixture 变化。

| 字段 | 类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
| `path` | `string` | 是 | — | fixture 文件路径，相对于 `task.yaml` 解析。 |
| `digest` | `string \| null` | 否 | `null` | 期望的 SHA-256 十六进制摘要。若提供，引擎在注入前校验文件，并将 digest 记录在 run 结果中用于可比性检查。 |

```yaml{8-13}
workspace:
  type: git_repo
  path: ./fixtures/repo
  ref: HEAD
  isolation_level: logical
  fixtures:
    - path: ./fixtures/data/users.csv
      digest: "e3b0c44298fc1c149afb..."    # SHA-256 of the file
    - path: ./fixtures/data/config.json
      digest: null                           # no verification
```

::: tip 为什么 digest 很重要
micro-eval 将 fixture digest 作为 SameStartSnapshot 可比性检查的一部分。只有 fixture digest 匹配的两次 run 才被视为可比较。若不提供 digest，fixture 的变化将无法被检测到，进而导致趋势分析在不知情的情况下失效。
:::

---

## ToolchainSpec

记录 agent 环境使用的运行时和 lockfile。引擎对这些文件进行哈希计算并将指纹存储在 run 结果中。趋势分析使用该指纹，当 toolchain 发生变化时将 run 标记为 `not_comparable`。

| 字段 | 类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
| `runtime` | `string \| null` | 否 | `null` | 运行时标识字符串，例如 `python3`、`node`，仅供参考。 |
| `lockfile` | `string \| null` | 否 | `null` | lockfile 路径（例如 `requirements.txt`、`package-lock.json`），引擎对该文件进行 SHA-256 哈希并记录指纹。 |

```yaml{10-12}
workspace:
  type: git_repo
  path: ./fixtures/python-project
  ref: HEAD
  isolation_level: logical
  setup:
    - [pip, install, -r, requirements.txt]
  toolchain:
    runtime: python3
    lockfile: ./fixtures/python-project/requirements.txt
```

---

## RubricSpec

定义 LLM judge 评分的标准。rubric 仅在确定性 expectations 通过（或不存在）后才会被评测。人工标注随时可以覆盖 LLM 分数。

| 字段 | 类型 | 必填 | 默认值 | 描述 |
|---|---|---|---|---|
| `text` | `string` | 是 | — | 描述"好的输出"应该是什么样子的自然语言文本，原文发送给 LLM judge。 |
| `dimensions` | `(string \| dict)[]` | 否 | `[]` | 有序的评分维度列表，每项可以是纯字符串名称，或包含 `name` 和可选 `weight`（float，默认 `1.0`）的 dict。 |

```yaml
rubric:
  text: |
    Evaluate the agent's response on the following criteria:
    1. Accuracy — does it correctly describe what changed?
    2. Brevity — is it concise without losing meaning?
    3. Actionability — does a reviewer know what to do next?
  dimensions:
    - accuracy
    - brevity
    - { name: actionability, weight: 0.5 }
```

rubric 也可以用纯字符串的简写形式提供：

```yaml
rubric: "The summary must be accurate, concise, and actionable."
```

::: tip 评测流程
引擎按以下顺序执行检查：
1. 确定性 `expectations` — 速度快，无需 API 调用
2. 使用 `rubric` 的 LLM judge — 仅在设置了 `expected_output` 或 `rubric` 时执行
3. 人工标注 — 在 UI 中始终可用，覆盖 LLM 分数
:::

---

## 完整示例

### 最简 task

```yaml
id: hello-world
name: Hello World

input_payload: |
  Print the text "Hello, World!" and nothing else.

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "Hello, World!"
    stream: output
```

### 使用 git workspace 的代码编辑 task

```yaml
id: add-type-hints
name: Add type hints to Python function

description: |
  Agent must add PEP-484 type annotations to a bare Python function
  and ensure mypy passes with no errors.

input_payload: |
  Add complete type hints to the function in src/utils.py.
  Run `mypy src/utils.py` to verify — it must exit 0.

workspace:
  type: git_repo
  path: ./fixtures/python-project
  ref: add-type-hints-base
  isolation_level: os_policy
  trust_level: semi_trusted
  network_policy: none
  toolchain:
    runtime: python3
    lockfile: ./fixtures/python-project/requirements.txt

expectations:
  - type: exit_code
    value: 0
  - type: command
    command: [mypy, src/utils.py, --strict]
    cwd: "{output_dir}"
    timeout_s: 30.0

rubric:
  text: |
    Evaluate whether the type hints are complete, correct, and idiomatic.
    Partial hints that silence mypy by casting to Any are not acceptable.
  dimensions:
    - completeness
    - correctness
    - { name: idiomatic_style, weight: 0.5 }

business_impact_tier: 2
tags: [python, type-safety]
revision_id: v2
```

### 带 fixtures 的文件生成 task

```yaml
id: generate-report
name: Generate CSV summary report

description: Agent reads raw transaction data and writes a summary CSV.

input_payload: |
  Read the file at input/transactions.csv.
  Write a summary report to output/summary.csv with columns:
  date, total_amount, transaction_count.
  One row per calendar day. Sort ascending by date.

workspace:
  type: files
  files:
    - ./fixtures/transactions.csv
  setup:
    - [mkdir, -p, output]
  isolation_level: logical
  fixtures:
    - path: ./fixtures/transactions.csv
      digest: "abc123def456..."

expected_output: "date,total_amount,transaction_count"

expectations:
  - type: exit_code
    value: 0
  - type: file_exists
    path: output/summary.csv
  - type: contains
    value: "date,total_amount,transaction_count"
    stream: output

business_impact_tier: 3
tags: [data-processing, csv]
```

### 对抗性/不可信 task（远程 VM）

```yaml
id: eval-untrusted-agent
name: Run untrusted code in isolated VM

input_payload: |
  Solve the following coding challenge and print the result to stdout.
  {{challenge_text}}

workspace:
  type: blank
  isolation_level: vm
  trust_level: adversarial
  network_policy: none

expectations:
  - type: exit_code
    value: 0

tags: [sandboxed, untrusted]
```

::: warning vm 隔离需要凭证
`isolation_level: vm` 使用 E2B 或 Modal 作为远程 provider。若未配置 provider 凭证，run 会立即失败，不会回退到较低隔离级别。使用前请设置 `MICRO_EVAL_SECRET_E2B_API_KEY` 或 `MICRO_EVAL_SECRET_MODAL_TOKEN`。
:::

---

## 字段快速参考

### ExpectationSpec — type 取值

| `type` | 检查内容 | 关键字段 |
|---|---|---|
| `exit_code` | agent 进程退出码 | `value`（int） |
| `contains` | agent 输出中的子字符串 | `value`（string）、`stream` |
| `file_exists` | workspace 中是否存在文件 | `path` |
| `command` | 外部命令退出码为 0 | `command`（argv 列表）、`cwd`、`timeout_s` |

### WorkspaceSpec — type 取值

| `type` | 适用场景 | 必填字段 |
|---|---|---|
| `blank` | 从零生成 | 无 |
| `files` | 静态输入文件 | `files` |
| `git_repo` | 代码编辑、agentic coding | `path` |

### WorkspaceSpec — isolation_level 取值

| `isolation_level` | 后端 | 可用性 |
|---|---|---|
| `logical` | git worktree | 始终可用 |
| `os_policy` | Seatbelt / Bubblewrap | macOS / Linux；不可用时优雅降级 |
| `container` | 预留 | 尚未实现 |
| `vm` | E2B / Modal | 需要凭证；无回退 |
