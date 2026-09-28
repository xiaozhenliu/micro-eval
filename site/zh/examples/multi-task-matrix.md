# 多任务矩阵

演示完整的二维评测矩阵：**2 个配置 × 3 个任务 × 2 次重复 = 12 个单元格**。全部四种期望类型均被覆盖，workspace 的 setup 命令在每次 agent 调用前执行，run 结果特意产生 `inconclusive` 决策——展示 micro-eval 如何将部分失败暴露出来而非隐藏。

::: tip 无需 API 密钥
本示例完全离线运行，使用确定性的 mock agent，无需 LLM 凭证或外部服务。
:::

## 你将学到什么

- 多任务评测如何展开为完整的结果矩阵
- 全部四种期望类型（`exit_code`、`contains`、`file_exists`、`command`）及其适用场景
- `setup` 命令如何在 agent 启动前准备 workspace
- caveat 系统如何暴露部分失败并设置决策状态
- `inconclusive` 的含义以及如何读取通过率表格

## 运行示例

```bash
# 在仓库根目录执行
python examples/run-example.py --example multi-task-matrix
```

启动器依次执行 `validate` → `run` → `list` → 文本报告 → HTML 报告。完成后：

- 在浏览器中打开 `examples/multi-task-matrix/report.html` 查看矩阵。
- `checker-alpha`（基线）在全部三个任务上显示 **PASS**。
- `checker-beta`（候选）在 `generate-report` 上显示 **FAIL**，其余两个任务为 PASS。
- 整体决策为 `inconclusive`。

若要在 Web UI 中查看结果：

```bash
python examples/run-example.py --example multi-task-matrix --ui
```

这会打开 `http://localhost:3000`，展示完整矩阵视图、逐单元格 trace 以及决策面板。

## 文件结构

```
examples/multi-task-matrix/
├── eval.mock.yaml                  # 2 configs × 3 tasks × 2 reps
├── run.py                          # 一键运行脚本（由 run-example.py 调用）
├── tasks/
│   ├── check-style.yaml            # exit_code 期望 + setup 命令
│   ├── find-bugs.yaml              # contains + file_exists 期望
│   └── generate-report.yaml        # command 期望
└── workspace/
    ├── sample-project/
    │   ├── main.py                 # 含风格问题和隐藏 bug 的 Python 源文件
    │   ├── utils.py
    │   └── tests/test_main.py
    └── scripts/
        ├── mock-good-checker.py    # 基线：全部三个任务通过
        └── mock-flaky-checker.py   # 候选：故意在 generate-report 上失败
```

## 评测配置

顶层配置声明两个 configuration 并引用三个任务文件：

```yaml
project_name: multi-task-matrix-mock
description: Offline smoke showing multi-task matrices, all 4 expectation types, setup commands, and caveats.

configurations:
  - id: checker-alpha
    name: Style Checker Alpha
    role: baseline
    repetitions: 2
    agent:
      name: Style Checker Alpha
      command: ["{python}", "workspace/scripts/mock-good-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30

  - id: checker-beta
    name: Style Checker Beta
    role: candidate
    repetitions: 2
    agent:
      name: Style Checker Beta
      command: ["{python}", "workspace/scripts/mock-flaky-checker.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30

tasks:
  - tasks/check-style.yaml
  - tasks/find-bugs.yaml
  - tasks/generate-report.yaml
```

`{python}` 占位符会解析为 micro-eval 当前使用的 Python 解释器。`{output_file}` 占位符在设置 `output_mode: file` 时于执行期注入——指向每个单元格的 artifact 输出目录中的文件路径。

## 四种期望类型

### 1. `exit_code` — check-style 任务

最简单的契约：agent 进程必须以指定的退出码退出，任何其他退出码均为 FAIL。

```yaml{3-4}
# tasks/check-style.yaml
expectations:
  - type: exit_code
    value: 0
```

当 agent 是已通过退出状态表示成功或失败的 CLI 工具时，使用 `exit_code`——例如 linter、测试运行器、编译器等类似工具。

### 2. `contains` — find-bugs 任务

agent 的输出（写入 `{output_file}` 的文件，或 `output_mode: stdout` 时的 stdout）必须包含特定字符串。

```yaml{3-5}
# tasks/find-bugs.yaml
expectations:
  - type: contains
    stream: output
    value: "BUG_FOUND"
```

当你想断言 agent 产生了特定 token 或标记，而不关心周围内容时，使用 `contains`。适用于输出结构化标签的 agent，例如 `BUG_FOUND`、`TASK_COMPLETE` 或 `VERDICT:`。

### 3. `file_exists` — find-bugs 任务

agent 完成后，指定文件必须存在于 artifact 输出目录中。`{output_dir}` 占位符解析为 `MICRO_EVAL_OUTPUT_DIR`——workspace 清理后仍会保留的逐单元格目录。

```yaml{3-4}
# tasks/find-bugs.yaml
expectations:
  - type: file_exists
    path: "{output_dir}/bugs-report.txt"
```

::: warning 将 artifact 写入 `MICRO_EVAL_OUTPUT_DIR`，而非 workspace 的 CWD
workspace 目录（`workspace/`）是临时的，run 结束后可能被清理。agent 写入其中的文件不会在验证阶段存活。agent 必须将持久化 artifact（报告、日志文件、生成的代码等）写入 `MICRO_EVAL_OUTPUT_DIR` 环境变量所指定的路径。
:::

### 4. `command` — generate-report 任务

agent 完成后运行一条任意命令（以普通 argv 列表指定），该命令必须以退出码 0 退出。`cwd` 字段将命令的工作目录限定为 artifact 输出目录。

```yaml{3-6}
# tasks/generate-report.yaml
expectations:
  - type: command
    argv: ["python3", "-c", "import json; json.load(open('report/summary.json'))"]
    cwd: "{output_dir}"
    timeout_s: 10
```

这条命令验证 `report/summary.json` **存在**且为合法 JSON——无需 task YAML 了解具体 schema。你可以使用主机上任何可用的程序：`jq`、`diff`、自定义验证脚本或 schema 校验器。

::: tip `command` 作为灵活验证器
`command` 是表达能力最强的期望类型。由于 argv 列表直接执行——无 shell 插值——你可以从系统路径上的任意工具组合验证器。命令返回非零退出码即为 FAIL。
:::

## Workspace Setup 命令

`check-style` 任务使用 `setup` 在 agent 启动前执行验证步骤：

```yaml{4-6}
# tasks/check-style.yaml
workspace:
  type: files
  files:
    - workspace
  setup:
    - ["test", "-d", "workspace/sample-project"]
```

setup 命令在单元格的 workspace 根目录中按顺序执行，在 agent 进程启动之前运行。每条命令是普通的 argv 列表——无 shell 插值——并支持 `{python}` 表示当前活跃的 Python 解释器。如果任何 setup 命令以非零退出码退出，该单元格将被标记为错误，agent 不会运行。

## 命令占位符

所有可执行命令均为 argv 数组。占位符替换在每个参数级别进行，绝不调用 shell。

| 命令入口点 | 支持的占位符 |
| --- | --- |
| Agent 命令 | `{python}`, `{input_file}`, `{output_file}`, `{output_dir}` |
| Workspace setup 命令 | `{python}` |
| Command 期望 | `{python}`, `{output_dir}` |

`{python}` 始终解析为运行 micro-eval 的当前 Python 解释器。由于 setup 在单元格 artifact 路径可用之前运行，输入/输出占位符被故意限制在 agent 和验证上下文中。

setup 命令的适用场景：
- 验证所需文件或目录是否存在
- 安装依赖（`["pip", "install", "-r", "requirements.txt"]`）
- 运行数据库迁移或种子脚本
- 在 agent 使用 workspace 前复制或生成 fixture 数据

## Inconclusive 结果的工作原理

本示例被设计为产生清晰、可读的部分失败：

| 配置 | check-style | find-bugs | generate-report | 通过率 |
|---|:---:|:---:|:---:|:---:|
| checker-alpha（基线） | PASS | PASS | PASS | 100%（6/6 个单元格） |
| checker-beta（候选） | PASS | PASS | **FAIL** | 67%（4/6 个单元格） |

`checker-beta` 故意跳过创建 `report/summary.json`。`command` 期望在 artifact 输出目录中运行 `python3 -c "import json; json.load(open('report/summary.json'))"` 并收到 `FileNotFoundError`，使得 `generate-report` 任务的两次重复均为 FAIL。

最终决策状态为 **`inconclusive`**，置信度低。当没有配置 `decision_threshold` 时，micro-eval 不会因单个任务失败而自动判定为回归，但会在矩阵和通过率摘要中清晰地展示差异：

```
checker-alpha  @1=100%  (baseline)
checker-beta   @1= 67%  (candidate)
decision: inconclusive (low)
```

::: tip 何时 `inconclusive` 是正确结果
`inconclusive` 意味着 micro-eval 检测到了差异，但信号不足以判定为回归或改进。可在评测配置中添加 `decision_threshold`、增加 `repetitions`，或接入 LLM judge 来提升置信度，从而获得更明确的决策。
:::

## 护栏（Guardrails）

本示例以有界并发和逐单元格输出上限运行：

```yaml
guardrails:
  max_concurrency: 2
  timeout_s: 60
  output_cap_bytes: 1048576    # 每个输出文件 1 MiB
  artifact_cap_bytes: 1048576  # 每个 artifact 目录 1 MiB
  stop_on_cell_error: false
```

`stop_on_cell_error: false` 允许 run 在单个单元格失败时继续执行——这里很重要，因为我们希望 `checker-beta` 在某个任务上失败，而不中止整个矩阵。

## 切换输出模式

本示例两个配置均使用 `output_mode: file`。若要尝试其他模式，可编辑 `eval.mock.yaml` 中的 agent 配置块：

::: code-group

```yaml [file (default)]
agent:
  command: ["{python}", "workspace/scripts/mock-good-checker.py", "{output_file}"]
  input_mode: stdin
  output_mode: file
  timeout_s: 30
```

```yaml [stdout]
agent:
  # 从命令中移除 {output_file}——agent 改为写入 stdout。
  command: ["{python}", "workspace/scripts/mock-good-checker.py"]
  input_mode: stdin
  output_mode: stdout
  timeout_s: 30
```

```yaml [directory]
agent:
  # agent 的 CWD 成为输出目录。
  # 写入其中的所有文件均作为 artifact 被捕获。
  command: ["{python}", "workspace/scripts/mock-good-checker.py"]
  input_mode: stdin
  output_mode: directory
  timeout_s: 30
```

:::

`{output_file}` 占位符仅在 `output_mode: file` 时注入。使用 `stdout` 或 `directory` 模式时，请从 `command` 列表中移除它。

## 能力汇总

| 演示的能力 | 位置 |
|---|---|
| 2 个配置 × 3 个任务 × 2 次重复 = 12 个单元格 | `eval.mock.yaml` |
| `exit_code` 期望 | `tasks/check-style.yaml` |
| `contains` 期望 | `tasks/find-bugs.yaml` |
| `file_exists` 期望 | `tasks/find-bugs.yaml` |
| `command` 期望 | `tasks/generate-report.yaml` |
| Workspace `setup` 命令（argv 列表） | `tasks/check-style.yaml` |
| `files` workspace 类型 | 全部三个任务文件 |
| Caveat 系统（部分失败） | `checker-beta` 在 `generate-report` 上 |
| `inconclusive` 决策状态 | run 完成后的 `decision.json` |
| `stop_on_cell_error: false` 护栏 | `eval.mock.yaml` |

## 下一步

- **扩大规模**：向 `tasks:` 列表添加更多任务，或增加 `repetitions`，观察矩阵如何增长。
- **提升置信度**：在 `evaluation:` 块中添加 `decision_threshold`，将 `inconclusive` 结果转化为明确的 `regressed` 或 `improved` 判定。
- **添加 LLM judge**：配置 OpenAI 密钥并启用 `judge.enabled: true`，对超出确定性期望范围的输出进行评分。
- **尝试 workspace 隔离**：参阅 [Git Workspace 隔离](/zh/examples/git-workspace-isolation) 示例，了解 OS 策略沙箱和 fixture digest 追踪。
