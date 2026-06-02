# 开发指南

本文不是正式开发规范。正式开发规范以 `docs/engineering/` 文件夹中的内容为准；如本文与 `docs/engineering/` 冲突，按 `docs/engineering/` 执行。

本文面向继续开发 `micro-eval` 的工程师。它描述当前代码库的可运行状态、主要模块、开发流程和验收命令；长期产品/架构范围仍以仓库根目录 `AGENTS.md` 中列出的权威文档为准。

当前版本：`0.1.2`

## 开发原则

- 始终在 `dev` 分支上做日常开发；`main` 是干净发布分支。
- 禁止使用 TDD 方法。开发顺序是：理解规格与用户路径，设计模块/文件边界，实现可运行垂直切片，最后用测试、构建和真实产物验证。
- DeepEval 只作为可选评分库，不作为执行编排层。
- agent 输入必须通过 stdin 或 runner-owned 文件传入；禁止 shell 字符串插值。
- 每次涉及 subprocess、env、artifact、stdout/stderr、workspace 的改动，都必须按 `docs/engineering/security-guidelines.md` 做安全检查。
- Python 代码注释和 git commit message 使用英文；面向用户的回复使用简体中文。

## 前置要求

- Python 3.11+
- `uv`
- Node.js 18+，用于本地 Web UI
- Git，workspace 隔离 helper 依赖 git worktree

## 本地开发环境

### Python CLI 和执行引擎

```bash
# 安装核心包
uv pip install -e .

# 安装开发、评分和观测可选依赖
uv pip install -e ".[dev,scoring,observability]"

# 验证 CLI
uv run micro-eval --help

# 运行 Python 测试
uv run pytest -q
```

### Web UI

```bash
cd ui
npm install
npm run dev
```

默认开发地址是 `http://localhost:3000`。UI 默认把项目根目录解析为 `ui/..`，并读取 `<project-root>/.micro-eval/runs/`。需要读取其他项目目录时使用：

```bash
MICRO_EVAL_PROJECT_ROOT=/path/to/project npm run dev
```

通过 CLI 也可以启动 UI：

```bash
uv run micro-eval ui --port 3000
```

## 仓库结构

```text
micro-eval/
├── src/micro_eval/
│   ├── cli/
│   │   ├── main.py          # Typer app 和命令注册
│   │   ├── run.py           # run 命令：加载配置、执行、评分、保存 JSON
│   │   └── report.py        # report 命令：run JSON -> 静态 HTML
│   ├── config/
│   │   └── loader.py        # eval.yaml 和 task YAML 加载
│   ├── engine/
│   │   ├── runner.py        # asyncio subprocess 执行层
│   │   ├── scorer.py        # MVP 自动评分逻辑
│   │   └── workspace.py     # git worktree helper，尚未接入 run 主流程
│   └── models/
│       └── schema.py        # Pydantic v2 领域模型
├── tests/
│   ├── unit/                # schema/config/runner 单元测试
│   └── e2e/                 # config -> run -> score -> JSON 端到端测试
├── ui/
│   └── src/
│       ├── app/             # Next.js App Router 页面
│       ├── components/      # RunList、ComparisonTable、AnnotationPanel
│       └── lib/             # 文件数据访问 + zod schema
├── docs/engineering/        # 按场景读取的工程规范
├── docs/superpowers/specs/  # 长期架构、MVP profile、测试架构权威来源
├── docs/analysis/           # repo/产品研究与对比分析产物
├── eval.yaml.example        # eval.yaml 示例
└── pyproject.toml
```

## 当前架构

```text
CLI (Typer)
  run.py
    -> load_config() / load_tasks()
    -> AgentRunner.run_eval()
    -> Scorer.score() / judge_pass_fail()
    -> .micro-eval/runs/<run-id>.json

  report.py
    -> Run Pydantic parse
    -> static HTML report

Execution Engine
  AgentRunner
    -> build argv with shlex.split()
    -> pass task input via stdin or {input_file}
    -> inject MICRO_EVAL_OUTPUT_DIR / MICRO_EVAL_OUTPUT_FILE
    -> create_subprocess_exec()
    -> cap stdout/stderr at 10 MB each
    -> redact agent.env values before persisted text output
    -> write invocation artifacts under .micro-eval/artifacts/<run-id>/

Web UI (Next.js)
  ui/src/lib/api.ts
    -> reads .micro-eval/runs/*.json
    -> validates with ui/src/lib/schema.ts
  pages/components
    -> list runs
    -> show task x agent comparison table
    -> keep current annotation UI state in localStorage
```

## 当前数据流

1. `micro-eval run --config eval.yaml` 加载 `eval.yaml`。
2. `tasks_dir` 相对配置文件所在目录解析。
3. 执行层运行 `tasks × [baseline, candidate]`。
4. 每个 invocation 生成 stdout/stderr artifacts 和可选 output artifacts。
5. `Scorer` 基于 `expected_output` 做精确匹配或包含匹配。
6. run JSON 写入配置声明的 `output_dir`，默认 `.micro-eval/runs/`。
7. `micro-eval report` 从 run JSON 生成 HTML。
8. Web UI 读取 `.micro-eval/runs/*.json` 并用 zod 校验。

## CLI 命令

### `micro-eval run`

```bash
uv run micro-eval run --config eval.yaml
uv run micro-eval run --config eval.yaml --no-parallel
uv run micro-eval run --config eval.yaml --verbose
```

当前实现支持：

| 选项 | 默认值 | 说明 |
|---|---:|---|
| `--config`, `-c` | `eval.yaml` | 配置文件路径 |
| `--parallel / --no-parallel` | `--parallel` | 是否并行执行 |
| `--verbose`, `-v` | `false` | 预留详细输出开关 |

注意：`eval.yaml` 中的 `parallel` 字段可以被加载到 `ProjectConfig`，但当前 CLI 的 `parallel` Typer 默认值会直接传入执行层；如果没有显式传 `--no-parallel`，运行会并行执行。

### `micro-eval report`

```bash
uv run micro-eval report .micro-eval/runs/<run-id>.json
uv run micro-eval report .micro-eval/runs/<run-id>.json --output report.html
```

当前 report 是轻量静态 HTML：包含 run 元信息、baseline/candidate、执行顺序、任务数和结果表。Decision、caveats、artifact 深链和人工评分持久化仍属于后续 MVP profile 工作。

### `micro-eval ui`

```bash
uv run micro-eval ui --port 3000
```

该命令在当前工作目录下寻找 `ui/` 并执行 `npm run dev -- --port <port>`。

## eval.yaml 契约

最小配置：

```yaml
project_name: my-agent-eval

baseline:
  name: baseline
  command: "cat"
  input_mode: stdin
  output_mode: stdout
  timeout_s: 300
  env: {}

candidate:
  name: candidate
  command: "cat"
  input_mode: stdin
  output_mode: stdout
  timeout_s: 300
  env: {}

tasks_dir: tasks
output_dir: .micro-eval/runs
parallel: true
timeout_s: 300
```

Agent 字段：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---:|---|
| `name` | string | section name | 显示名称，也是当前 artifact path 的一部分 |
| `command` | string | 必填 | agent 命令字符串，经 `shlex.split()` 转为 argv |
| `input_mode` | `stdin` / `file` | `stdin` | task 输入传递方式 |
| `output_mode` | `stdout` / `file` / `directory` | `stdout` | scoring output 选择方式 |
| `timeout_s` | number | `300.0` | 单个 invocation 超时 |
| `env` | map | `{}` | 注入 agent subprocess 的环境变量 |

`command` 支持的占位符：

| 占位符 | 含义 |
|---|---|
| `{input_file}` | `input_mode: file` 时由 runner 写入的输入文件 |
| `{output_file}` | `output_mode: file` 的首选输出文件 |
| `{output_dir}` | 当前 invocation 的 artifact 目录 |

Runner 还会注入：

| 环境变量 | 含义 |
|---|---|
| `MICRO_EVAL_OUTPUT_FILE` | 与 `{output_file}` 相同 |
| `MICRO_EVAL_OUTPUT_DIR` | 与 `{output_dir}` 相同 |

## Task YAML 契约

每个 task 是 `tasks_dir` 下的一个 `.yaml` 文件：

```yaml
id: echo-001
name: Echo smoke
description: Verify echo behavior
input_payload: "hello"
expected_output: "hello"
rubric: "Output must match the input."
business_impact_tier: 3
tags: [smoke]
```

| 字段 | 必填 | 说明 |
|---|---:|---|
| `id` | 否 | 默认使用文件名 stem |
| `name` | 否 | 默认使用文件名 stem |
| `description` | 否 | 默认空字符串 |
| `input_payload` | 是 | 传给 agent 的输入 |
| `expected_output` | 否 | 设置后参与自动评分 |
| `rubric` | 否 | 人工评分标准 |
| `business_impact_tier` | 否 | 默认 `3` |
| `tags` | 否 | 默认空列表 |

## 产物布局

当前 run JSON 和 invocation artifacts 分开保存：

```text
.micro-eval/
├── runs/
│   └── run-YYYYMMDDTHHMMSSZ-<random>.json
└── artifacts/
    └── run-YYYYMMDDTHHMMSSZ-<random>/
        └── <task-id>--<role>--<agent-name>/
            ├── input.txt      # file input mode only
            ├── stdout.txt
            ├── stderr.txt
            ├── output.txt     # preferred file output path
            └── ...            # directory/file output artifacts
```

当前 `RunResult` 已记录 `stdout_summary`、`stderr_summary`、`stdout_ref`、`stderr_ref`、`exit_code`、`output_dir`、`output_artifacts` 和 `failure_mode`。完整说明见 `docs/invocation-evidence.md`。

## 安全边界

涉及执行层的改动必须至少检查：

- shell interpolation：新增 subprocess 调用必须使用 argv list；不得使用 `create_subprocess_shell`。
- secrets redaction：stdout/stderr 和文本 artifacts 持久化前必须脱敏；当前实现用 `agent.env` 的值做替换。
- workspace 边界：当前 `AgentRunner` 在 `work_dir` 下运行，`WorkspaceManager` 仍是 helper；把 worktree 接入主流程时必须确保 agent 只在分配 workspace 内执行。
- output caps：stdout/stderr 当前各自最多保留 10 MB；大 artifact 的上限和 manifest warning 仍未完整实现。
- binary artifacts：当前含 NUL 字节的文件会跳过 in-place redaction；后续 evidence/manifest 需要记录 warning。
- raw artifacts：UI/Decision 不应直接把未校验 raw artifact 当成可信结论。

交付报告中需要明确说明 secrets redaction、workspace 边界、shell interpolation 三项的处理方式。

## 测试与验证

常用命令：

```bash
# Python
uv run pytest -q
uv run pytest tests/unit/ -q
uv run pytest tests/e2e/ -q

# Web UI
cd ui && npm run lint
cd ui && npm run build
```

建议的变更级别验收：

| 变更类型 | 最低验收 |
|---|---|
| Python schema/config/runner/scorer | `uv run pytest -q` |
| CLI 行为或产物格式 | `uv run pytest -q` + 真实 `micro-eval run`/`report` smoke |
| Pydantic `Run`/`RunResult` 字段 | Python 测试 + 同步更新 `ui/src/lib/schema.ts` + UI build |
| UI 数据读取或组件 | `cd ui && npm run lint` + `cd ui && npm run build` |
| subprocess/env/artifact/workspace | Python 测试 + 安全 checklist + smoke artifact 检查 |

真实 smoke 可使用仓库 fixtures 或一个临时 eval 项目。示例：

```bash
uv run micro-eval run --config tests/fixtures/eval.yaml
uv run micro-eval report .micro-eval/runs/<run-id>.json
```

## 添加或修改功能

### 新增 CLI 命令

1. 在 `src/micro_eval/cli/` 下创建命令模块。
2. 使用 Typer 定义命令函数。
3. 在 `src/micro_eval/cli/main.py` 注册。
4. 增加验收测试和真实 CLI smoke。

### 修改执行层

1. 先读取 `docs/engineering/python-guidelines.md` 和 `docs/engineering/security-guidelines.md`。
2. 保持 task input 通过 stdin/file 传递。
3. 保持 subprocess argv list 执行。
4. 保持 stdout/stderr cap、timeout terminate/kill、cell 失败不阻断其他 cell 的行为。
5. 新增 artifact 字段时同步 Pydantic、zod、测试和文档。

### 修改 schema

1. 更新 `src/micro_eval/models/schema.py`。
2. 同步更新 `ui/src/lib/schema.ts`。
3. 确认可空性、enum 字符串、默认值一致。
4. 更新测试。当前仓库还没有完整 contract tests；schema 相关改动至少要覆盖 Python round-trip 和 UI build。

### 修改 Web UI

1. 先阅读 `ui/AGENTS.md`；Next.js 16/React 19 可能和旧经验不同。
2. 页面放在 `ui/src/app/`。
3. 组件放在 `ui/src/components/`。
4. 数据读取通过 `ui/src/lib/api.ts`，并经过 zod parse。
5. 人工评分等可信业务数据不要长期依赖 localStorage；当前 `AnnotationPanel` 是过渡实现。

## 当前已知边界

- `WorkspaceManager` 已存在，但 `micro-eval run` 主流程尚未使用 git worktree 隔离。
- Environment snapshot 当前只记录 Python version 和 timestamp；git commit/config hash 仍可能为 `null`。
- `eval.yaml` 的项目级 `timeout_s` 已加载，但当前执行使用 agent 级 `timeout_s`。
- `eval.yaml` 的 `parallel` 字段会被加载，但 CLI 默认 `--parallel` 会覆盖未显式传参的配置意图。
- artifact/evidence 仍是过渡层：没有 `manifest.json`、canonical `ArtifactRef`、`EvidenceItem`、`RunCell` 或 `DecisionReport`。
- Web UI 直接读取 run JSON 文件并做 zod 校验；还没有统一 RunStore/API route 抽象。
- HTML report 是轻量结果表，不代表完整 MVP Decision Layer。

## 权威文档路由

- 长期架构、不变量、Stable ID、证据模型：`docs/superpowers/specs/2026-06-02-unicorn-design.md` Part I。
- 当前 MVP 范围与迁移分期：`docs/superpowers/specs/2026-06-02-mvp-profile.md`。
- 测试架构：`docs/superpowers/specs/2026-06-02-test-architecture.md`。
- Python CLI/engine/schema/subprocess：`docs/engineering/python-guidelines.md`。
- Next.js/TypeScript/zod/UI data access：`docs/engineering/frontend-guidelines.md`。
- secrets/workspace/subprocess 安全：`docs/engineering/security-guidelines.md`。

不要在本文件重新定义上述文档的长期契约；这里只记录当前代码库如何开发、运行和验收。
