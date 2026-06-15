# 任务与期望

**task** 是 micro-eval 中评测的基本单元。每个 task 描述一个场景：交给 agent 的输入、agent 运行的环境，以及判断 agent 是否成功的规则。

Task 在 YAML 文件中定义，并由 `Run` 引用。执行 run 时，micro-eval 将 `Tasks × Configurations × Repetitions` 展开为结果矩阵，对每个 configuration 执行每个 task，次数由 `repetitions` 指定。

## 完整 Task 结构

```yaml
# tasks/refactor-extract-function.yaml
id: refactor-extract-function
name: "Extract helper function from monolith"
description: >
  Given a 200-line Python file, the agent should extract a
  clearly reusable helper into a separate function with a
  descriptive name and update all call sites.

input_payload: |
  Refactor the code in src/utils.py. Extract the date-parsing
  logic (lines 45-72) into a standalone function called
  `parse_iso_date`. Update every call site in the same file.

expected_output: |
  def parse_iso_date(value: str) -> datetime:
      ...

rubric:
  text: "Did the agent correctly extract the function without breaking existing behavior?"
  dimensions:
    - name: correctness
      weight: 0.5
      description: "All tests pass after the refactor"
    - name: naming
      weight: 0.2
      description: "Function name matches the specification"
    - name: call_sites
      weight: 0.3
      description: "Every call site in utils.py is updated"

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "def parse_iso_date"
    stream: stdout
  - type: file_exists
    path: "{output_dir}/src/utils.py"
  - type: command
    command: ["python", "-m", "pytest", "tests/", "-q"]
    cwd: "{output_dir}"

workspace:
  type: git_repo
  path: /path/to/your/project
  ref: main
  isolation_level: logical
  trust_level: semi_trusted
  network_policy: none
  setup:
    - ["pip", "install", "-e", "."]
  fixtures:
    - path: testdata/utils_original.py
      digest: sha256:abc123...
  toolchain:
    runtime: python3
    lockfile: requirements.txt

business_impact_tier: 2
tags: [refactor, python, extract-function]
revision_id: "2026-06-15-v1"
```

### 字段说明

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `id` | 是 | 路径安全的标识符，允许字符：`A-Za-z0-9_.:–`，项目内必须唯一。 |
| `name` | 是 | 在 UI 和报告中显示的人类可读名称。 |
| `description` | 否 | 对 task 测试内容的详细说明，显示在 run 详情页。 |
| `input_payload` | 是 | 作为任务输入传递给 agent 的文本或提示词。 |
| `expected_output` | 否 | 可选的参考答案，供 LLM judge 评分时用作黄金标准。 |
| `rubric` | 否 | 评分标准，可以是普通字符串，也可以是包含命名维度和权重的结构化对象。 |
| `expectations` | 否 | 在 LLM judge 运行前执行的确定性验证规则，验证失败会短路评分流程。 |
| `workspace` | 否 | 执行环境规格，默认为 `type: blank` 且 `isolation_level: logical`。 |
| `business_impact_tier` | 否 | `1`–`3`（整数），在报告中显示以辅助优先级排序，`1` 为最高优先级。 |
| `tags` | 否 | 自由格式列表，用于 `micro-eval list` 和 `--tag` 筛选。 |
| `revision_id` | 否 | 不透明字符串，用于追踪 task 定义随时间的变化。 |

## 四种期望类型

**Expectation** 是针对单元格输出评估的确定性、零 LLM 验证规则。Expectations 速度快、成本低、可复现——它们在 agent 进程退出后、调用 LLM judge 之前立即运行，是防御明显失败的第一道防线。

若任意 expectation 失败，该结果将被标记为 `failed`，结果矩阵中对应单元格的 LLM judge 将被跳过。

### `exit_code` — 进程退出状态

Agent 进程必须以指定的数字代码退出。

```yaml
expectations:
  - type: exit_code
    value: 0
```

对于预期 agent 成功完成的 task，使用 `value: 0`；如果专门测试错误处理场景，则使用非零值。

::: tip
几乎每个 task 都应包含 `exit_code: 0`。它能在浪费 LLM judge 预算之前，提前捕获崩溃、超时和子进程错误。
:::

### `contains` — 输出字符串匹配

指定的流必须包含给定的字符串。匹配区分大小写，按字面值匹配（不支持正则表达式）。

```yaml
expectations:
  - type: contains
    value: "Task completed successfully"
    stream: stdout

  - type: contains
    value: "parse_iso_date"
    stream: stdout

  - type: contains
    value: "ERROR"
    stream: stderr
```

**`stream` 可选值：**

| 值 | 检查对象 |
|---|---|
| `stdout` | Agent 进程的标准输出 |
| `stderr` | Agent 进程的标准错误 |
| `output` | stdout + stderr 合并（省略时默认） |

::: tip
当你希望断言 agent 产出了特定内容、而不受 stderr 日志行干扰时，使用 `stream: stdout` 而非 `output`。
:::

### `file_exists` — 输出文件存在性

Agent 完成后，给定路径的文件必须存在。使用 `{output_dir}` 作为 task 工作区目录的占位符——micro-eval 会在运行时将其替换为实际路径。

```yaml
expectations:
  - type: file_exists
    path: "{output_dir}/report.md"

  - type: file_exists
    path: "{output_dir}/src/utils.py"

  - type: file_exists
    path: "{output_dir}/dist/bundle.js"
```

::: warning
Agent 的工作目录是工作区根目录，与 `{output_dir}` 解析的路径相同。不要写相对于项目根目录的路径——agent 不在你的项目目录中运行。
:::

### `command` — 外部验证脚本

运行任意命令作为验证器。该命令必须以代码 `0` 退出，expectation 才算通过。这是最强大的 expectation 类型：它允许你运行现有的测试套件、linter、diff 检查或任何其他验证逻辑。

```yaml
expectations:
  - type: command
    command: ["python", "-m", "pytest", "tests/", "-q", "--tb=short"]
    cwd: "{output_dir}"

  - type: command
    command: ["npx", "tsc", "--noEmit"]
    cwd: "{output_dir}"

  - type: command
    command: ["git", "diff", "--exit-code"]
    cwd: "{output_dir}"

  - type: command
    command: ["bash", "scripts/validate_output.sh"]
    cwd: "{output_dir}"
```

**`command` expectations 的重要约束：**

- `command` 必须是列表——绝不能是 shell 字符串。micro-eval 直接将参数传递给子进程，不经过 shell，从而防止注入攻击和引号问题。
- 省略 `cwd` 时默认为 `{output_dir}`。
- 命令的 stdout 和 stderr 会被捕获并附加到 run 结果中以便调试，但不影响通过/失败的判定——只有退出码才有效。

::: warning
不要使用 `command: ["sh", "-c", "some command string"]`。如果需要 shell 特性，请写一个脚本文件，将其提交到 fixture，然后用 `command: ["bash", "scripts/my-check.sh"]` 调用。
:::

## Workspace 类型

**WorkspaceSpec** 定义了 run 中每个单元格启动时的执行环境。为使结果具有可比性，一次 run 中的每个单元格必须从相同的 WorkspaceSpec 启动——micro-eval 将 workspace 状态（fixture digest + toolchain fingerprint）哈希到 `SameStartSnapshot` 中，并用 `snapshot_mismatch` Caveat 标记存在差异的单元格。

`workspace` 块控制 agent 运行的环境。每个 workspace 都是隔离的：结果矩阵中每个 `(task, configuration, repetition)` 单元格都有自己独立的目录。

### `blank` — 空目录

Agent 在一个空的临时目录中启动。适用于预期 agent 从头创建一切内容的 task。

```yaml
workspace:
  type: blank
  isolation_level: logical
```

### `files` — 复制特定文件

micro-eval 在 agent 运行前将一组文件或目录复制到 workspace。Agent 看到的是干净的副本；它所做的任何修改不会影响源文件。

```yaml
workspace:
  type: files
  path: testdata/my-scenario/
  isolation_level: logical
  setup:
    - ["npm", "install"]
```

`path` 指向你项目中的目录，其内容会递归复制到 workspace 根目录。

### `git_repo` — 隔离的 worktree

micro-eval 从指定仓库的给定 ref 创建 git worktree。这是可复现性最强的 workspace 类型：精确的 commit 会被记录在 run 结果中，使得任何结果都可以精确复现。

```yaml{3-5}
workspace:
  type: git_repo
  path: /path/to/repo
  ref: main
  isolation_level: logical
  network_policy: none
  setup:
    - ["pip", "install", "-e", ".[dev]"]
  fixtures:
    - path: testdata/seed_data.sql
      digest: sha256:deadbeef...
  toolchain:
    runtime: python3
    lockfile: requirements.txt
```

::: tip
`ref` 可以是分支名、标签或完整的 commit SHA。使用完整 SHA 可获得最大可复现性，推荐用于回归基线。
:::

## 隔离级别

`isolation_level` 字段控制 workspace 与系统其余部分的隔离强度。

| 级别 | 机制 | 适用场景 |
|---|---|---|
| `logical` | git worktree——仅文件系统隔离 | 日常开发、可信 agent |
| `os_policy` | Seatbelt（macOS）/ Bubblewrap（Linux）——系统调用限制 | 需要 OS 级别的隔离但不想用容器运行时 |
| `container` | OCI 容器 | 已有 Docker/Podman 且需要完全隔离 |
| `vm` | E2B 或 Modal 远程 VM | 最强隔离；完全在你的机器之外运行 |

::: tip
`logical` 是默认值，无需额外工具。当你开始评测会进行文件系统或网络调用、需要加以限制的 agent 时，可升级为 `os_policy`。
:::

::: warning
`container` 和 `vm` 级别需要外部凭证（`MICRO_EVAL_SECRET_E2B_API_KEY`、`MICRO_EVAL_SECRET_MODAL_TOKEN_ID` 等）。如果所需凭证缺失，micro-eval 会立即报错——对于这两个级别，它不会静默降级为更弱的隔离级别。
:::

## Setup 命令

可选的 `setup` 块在 agent 进程启动前，在 workspace 中依次运行一系列命令。每个条目都是一个 `argv` 列表。

```yaml
workspace:
  type: git_repo
  path: /path/to/repo
  ref: main
  setup:
    - ["pip", "install", "-e", ".[dev]"]
    - ["npm", "install", "--prefix", "frontend"]
    - ["python", "scripts/seed_db.py"]
```

Setup 命令按顺序运行，若任意命令以非零退出，则执行停止。其输出会被捕获并以 `setup_log` 的形式包含在 run 结果中。

::: warning
Setup 命令在 workspace 内运行，而非你的项目根目录。每条 setup 命令的工作目录是 workspace 根目录。如果你的 setup 脚本引用了相对于项目根目录的文件，请通过 `fixtures` 将这些文件复制进来，或使用绝对路径。
:::

## Fixtures

Fixtures 允许你将特定文件版本注入 `git_repo` workspace，覆盖仓库在 `ref` 处的内容。每个 fixture 条目指定文件路径（相对于你的项目）和可选的摘要用于完整性校验。

```yaml
workspace:
  type: git_repo
  path: /path/to/repo
  ref: main
  fixtures:
    - path: testdata/initial_state.py
      digest: sha256:abc123...
    - path: testdata/config_v2.yaml
      digest: sha256:def456...
```

`digest` 字段可选但推荐填写。填写后，micro-eval 会在 run 开始前验证 fixture 文件与 digest 是否匹配，并将其记录在 SameStartSnapshot 中——该快照包含用于判断两个结果是否可比的所有维度。

## `{output_dir}` 占位符

字符串 `{output_dir}` 在运行时会被替换为当前 `(task, configuration, repetition)` 单元格的 workspace 目录的绝对路径。它可用于：

- `file_exists` → `path`
- `command` → `cwd`

::: tip
始终使用 `{output_dir}` 而非硬编码路径。micro-eval 为每个单元格创建独立的新目录，实际路径包含 run ID 和重复次数索引等 run 特定的组成部分。
:::

## Rubric 结构

`rubric` 字段用于引导 LLM judge，可以是普通字符串或结构化对象。

::: code-group

```yaml [简单 rubric]
rubric: >
  Did the agent produce a working solution that handles edge cases
  and follows the project's naming conventions?
```

```yaml [结构化 rubric]
rubric:
  text: "Evaluate the agent's refactoring quality."
  dimensions:
    - name: correctness
      weight: 0.5
      description: "Tests pass; behavior is preserved"
    - name: readability
      weight: 0.3
      description: "Code is clear and follows project style"
    - name: coverage
      weight: 0.2
      description: "All specified locations were updated"
```

:::

各维度权重之和必须为 1.0。LLM judge 使用 rubric 文本和维度，对每个维度产出 0 到 1 之间的分数，再计算加权平均值。

## 验证 → Judge → 人工 流水线

micro-eval 分三个阶段评估每个结果：

1. **确定性验证**（`expectations[]`）——最先运行，无 LLM 成本，速度快。
2. **LLM judge**——仅在所有 expectations 通过后运行，使用 `rubric` 给出 0–1 的分数。
3. **人工标注**——可选的覆盖项。人工审核者可在 UI 中将某个结果标记为正确或错误，该标注在决策中优先于 LLM 分数。

结果矩阵中最终的单元格状态反映了全部三个阶段。如果需要排查令人意外的结果，run 详情页提供了完整 trace、agent 的 stdout/stderr 以及所有人工标注的链接。
