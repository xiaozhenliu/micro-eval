# 快速开始

本指南带你完成 micro-eval 的安装，并在十分钟内运行第一次评测。

## 前置条件

| 要求 | 版本 | 说明 |
|---|---|---|
| Python | 3.11+ | CLI 和引擎必需 |
| [uv](https://docs.astral.sh/uv/) | 最新版 | 推荐的包管理器 |
| Node.js | 18+ | 可选 — 仅 Web UI 需要 |

::: tip 为什么用 uv？
micro-eval 使用 `uv` 实现快速、可复现的依赖解析。如果你更习惯 `pip`，请参考下方的备用安装命令。
:::

## 安装

### 从源码安装

```bash
git clone https://github.com/xiaozhenliu/micro-eval.git
cd micro-eval
```

安装 Python 依赖：

::: code-group

```bash [uv（推荐）]
uv sync --all-extras
```

```bash [pip]
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[all]"
```

:::

安装 Web UI 依赖（可选）：

```bash
cd ui && npm install && cd ..
```

验证 CLI 可用：

```bash
uv run micro-eval --version
# micro-eval 0.3.2
```

::: tip Shell 别名
在你的 shell 配置文件中添加 `alias micro-eval="uv run micro-eval"`，后续就无需每次都输入 `uv run`。下方示例均假设已设置此别名。
:::

---

## 第一次评测演练

本演练使用内置脚手架评测一个简单命令——无需任何外部 API。

### 1. 初始化项目

在你想用作评测工作区的任意目录中运行 `init`：

```bash
micro-eval init --force
```

该命令会生成两个文件：

```
eval.yaml          ← 顶层项目配置
tasks/
  hello.yaml       ← 示例任务定义
```

查看生成的内容：

```yaml
# eval.yaml
project_name: my-eval

configurations:
  - id: baseline
    name: baseline
    role: baseline
    repetitions: 1
    agent:
      command: ["echo", "hello world"]
      input_mode: stdin
      output_mode: stdout
      timeout_s: 30

tasks:
  - tasks/hello.yaml

guardrails:
  max_concurrency: 2
  timeout_s: 30

evaluation:
  required_evaluators: [validator]
```

```yaml
# tasks/hello.yaml
id: hello
name: Hello echo
input_payload: "hello world"
workspace:
  type: blank

expectations:
  - type: exit_code
    value: 0
  - type: contains
    value: "hello"
```

::: tip Workspace 类型
`blank` 以空工作目录启动。其他选项包括 `files`（复制本地目录）和 `git_repo`（在指定 commit 处克隆仓库）。详见 [核心概念](/zh/guide/core-concepts)。
:::

### 2. 验证配置

运行前，确认配置和任务文件格式正确，并预览执行计划：

```bash
micro-eval validate
```

示例输出：

```
✓ eval.yaml      valid
✓ tasks/hello.yaml  valid

RunPlan
  Configurations : 1  (baseline)
  Tasks          : 1  (hello)
  Repetitions    : 1
  Total cells    : 1
```

::: warning 运行前修复错误
`validate` 会捕获 schema 错误、缺失的任务文件以及无效的 expectation 类型。每次编辑 `eval.yaml` 或任意任务文件后都应运行它。
:::

### 3. 执行矩阵

```bash
micro-eval run --max-concurrency 2
```

micro-eval 将 `Tasks × Configurations × Repetitions` 展开为 cell 矩阵并发执行（受 `--max-concurrency` 限制）：

```
Running 1 cell(s) with concurrency 2 …

  [1/1] hello × baseline × rep-1   ✓  0.12s

Run complete  run_id=r-20260615-001
  Passed  : 1
  Failed  : 0
  Decision: inconclusive
```

每个 cell 以 argv-only 方式传参执行你的命令（子进程），不进行 shell 字符串插值。

### 4. 列出历史 Run

```bash
micro-eval list
```

```
run_id           started              tasks  configs  status
r-20260615-001   2026-06-15 09:01:03  1      1        complete
```

### 5. 查看文本报告

```bash
micro-eval report --format text
```

```
Run r-20260615-001  ·  2026-06-15 09:01:03
Decision: inconclusive

┌──────────────┬────────────┬────────┬────────────┐
│ task         │ config     │ score  │ status     │
├──────────────┼────────────┼────────┼────────────┤
│ hello        │ baseline   │ 1.00   │ passed     │
└──────────────┴────────────┴────────┴────────────┘
```

### 6. 导出 HTML 报告

```bash
micro-eval report --format html --output report.html
```

在任意浏览器中打开 `report.html`，即可查看包含完整结果矩阵和逐 cell 详情的自包含、可分享报告。

---

## 运行内置示例

仓库自带一个可直接运行的示例，演示多配置对比：

```bash
python examples/run-example.py
```

该示例端到端运行一个小型评测矩阵并将 decision 输出到 stdout。它是了解真实 `eval.yaml` 在多配置、多任务场景下形态的良好参考。

---

## 启动 Web UI

Web UI 提供基于浏览器的界面，展示 `.micro-eval/` 中存储的所有 run：

```bash
micro-eval ui --port 3000
```

然后打开 [http://localhost:3000](http://localhost:3000)。

::: tip 仅限本地
Web UI 严格在本地运行——它直接读取 `.micro-eval/` JSON 文件，不发出任何外部网络请求。使用前需已安装 Node.js 18+ 并在安装阶段执行过 `cd ui && npm install`。
:::

UI 展示：
- **Run 列表** — 所有历史 run 的状态与 decision
- **矩阵视图** — 完整的 Tasks × Configurations 结果网格
- **Cell 详情** — 逐 cell 的 trace、stdout/stderr、成本及标注
- **趋势图** — 跨 run 的分数趋势，标注 drift 断点

---

## 团队服务器（可选）

对于希望共享评测结果、协作运行评测的团队，micro-eval 提供**服务器模式**，可将一台机器变为共享的评测服务器。

### 快速启动

```bash
# 启动团队服务器（Next.js + worker）
micro-eval serve --port 3000
```

团队成员通过浏览器访问 `http://<server-ip>:3000`。

### 服务器模式新增能力

- **Workspace** — 每位成员创建独立的 workspace，拥有各自的 `eval.yaml` 和 run 历史
- **模板** — 共享的只读模板库；成员从模板创建 workspace
- **Run 队列** — 成员在浏览器中将 run 加入队列，worker 进程串行执行
- **归属记录** — 每个 workspace 和 run 都记录创建者信息

### Workspace 管理

```bash
# 从本地 eval 项目创建模板
micro-eval template create ./my-eval-project --id my-template --name "My Template"

# 从模板创建 workspace
micro-eval workspace create --name "alice-eval" --owner alice --template my-template

# 列出所有 workspace
micro-eval workspace list
```

### 与本地模式的区别

| 方面 | `micro-eval ui`（本地） | `micro-eval serve`（服务器） |
|------|------------------------|------------------------------|
| 访问方式 | 仅限 localhost | 局域网（0.0.0.0） |
| 数据目录 | 项目中的 `.micro-eval/` | `~/.micro-eval-server/` |
| 用户 | 单用户 | 多成员 |
| 执行方式 | 直接 CLI | 通过 worker 串行队列 |
| 身份验证 | 无需 | 无（可信局域网） |

::: tip 无需迁移
本地模式与服务器模式相互独立。你可以在同一台机器上同时运行两者——它们使用独立的数据目录，互不干扰。
:::

完整说明请参阅[团队服务器指南](/zh/guide/team-server)。

---

## 检查磁盘上的结果

每次 run 都以纯 JSON 格式存储在 `.micro-eval/runs/{run_id}/` 下：

```
.micro-eval/
└── runs/
    └── r-20260615-001/
        ├── run.json        ← run 元数据、配置快照、耗时
        ├── decision.json   ← decision 状态 + 各维度分数
        ├── manifest.json   ← 所有 cell 及其文件路径列表
        └── cells/
            └── hello__baseline__rep-1/
                ├── result.json   ← 退出码、stdout、stderr、分数
                └── trace.json    ← Langfuse trace（已配置时存在）
```

**关键文件说明：**

`run.json` — 顶层记录，包含本次 run 使用的完整配置快照、开始/结束时间戳以及已解析的任务列表。

`decision.json` — run 级别的裁决结果。Decision 状态为以下之一：`improved`、`regressed`、`mixed`、`inconclusive`、`not_comparable` 或 `needs_human_review`。

`cells/` — 每个 `(task, configuration, repetition)` 三元组对应一个子目录。`result.json` 存储原始子进程输出及针对各 expectation 计算出的分数。`trace.json` 仅在配置了 Langfuse 时生成。

::: tip SQLite 索引
micro-eval 在 `.micro-eval/index.db` 维护一个 SQLite 索引，用于快速趋势查询。JSON 文件始终是唯一数据来源——索引可随时从 JSON 重建。
:::

---

## 下一步

- **[核心概念](/zh/guide/core-concepts)** — 深入理解 Task、Configuration、Run 以及结果矩阵
- **[设计系统](/zh/guide/design-system)** — 了解决策循环与核心对象
