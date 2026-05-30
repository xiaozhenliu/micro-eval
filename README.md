# micro-eval

面向 1–20 人 AI 小团队的 Agent/Skill 评测助手。把"我觉得这个 agent 更强"变成"它在哪些任务上更强、为什么、延迟多少、值不值得继续投"。

## 什么是"被评测对象"

micro-eval 评测的是**完整 agent 程序**，通过 shell command 调用。它不评测 LLM prompt 模板，而是评测可执行的 agent 系统。

支持的 agent 类型包括但不限于：
- **Claude Code CLI** — `claude -p "..." --output-file ...`
- **LangGraph workflow** — `python my_graph.py --task "..."`
- **CrewAI / AutoGen / 任何自定义脚本** — 只要能通过命令行调用

**重要：** LangGraph、CrewAI 等框架**不是** micro-eval 的依赖。它们是你自己的 agent 项目的依赖。micro-eval 只是用 subprocess 调用你的 agent 命令、收集输出、计算评分。就像 pytest 测试 Django 项目时不需要把 Django 装成 pytest 的依赖一样。

你的 agent 项目需要自己管理运行环境（Python 虚拟环境、依赖安装、API key 配置等）。micro-eval 通过 `eval.yaml` 中的 `env` 字段把必要的环境变量传递给 agent subprocess。

## 核心特性

- **A/B 对比执行** — 同一组任务同时跑 baseline 和 candidate，结果矩阵一目了然
- **自写执行层** — ~200 行 asyncio 编排，完全可控，不依赖外部 test runner
- **安全输入传递** — stdin/文件传参，禁止 shell 字符串插值
- **Workspace 隔离** — git worktree 保证每次 run 起点一致
- **并行/串行可选** — asyncio 并行执行，也支持 `--no-parallel` 串行调试
- **自动评分** — MVP 精确匹配 + 包含匹配；可扩展 DeepEval 自定义指标
- **HTML 报告** — 一条命令生成静态对比报告
- **本地 Web UI** — Next.js 仪表盘，浏览历史 run、查看对比表格
- **零外部依赖运行** — Langfuse/DeepEval 均为可选，核心功能开箱即用

## 快速开始

### 1. 安装

```bash
# 推荐使用 uv（Python 3.11+）
uv pip install -e .

# 或带可选依赖
uv pip install -e ".[scoring,observability,dev]"
```

### 2. 配置

复制示例配置并编辑：

```bash
cp eval.yaml.example eval.yaml
```

### 3. 创建任务

在 `tasks/` 目录下创建 YAML 文件：

```bash
mkdir tasks
```
创建 `tasks/hello.yaml`：

```yaml
id: hello-test
name: 基础回显测试
description: 验证 agent 能正确回显输入
input_payload: "你好，世界"
expected_output: "你好，世界"
rubric: 输出必须与输入完全一致
business_impact_tier: 3
tags: [smoke, basic]
```

### 4. 运行评测

```bash
micro-eval run --config eval.yaml
```

### 5. 查看结果

```bash
# 生成 HTML 报告
micro-eval report .micro-eval/runs/run-*.json

# 或启动 Web UI
micro-eval ui
```

## CLI 命令参考

### `micro-eval run`

执行一次评测，对比 baseline 与 candidate。

```bash
micro-eval run [OPTIONS]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `-c, --config` | `eval.yaml` | 配置文件路径 |
| `--parallel / --no-parallel` | `--parallel` | 是否并行执行 |
| `-v, --verbose` | `false` | 详细输出 |

输出：结果 JSON 保存到 `.micro-eval/runs/run-<timestamp>.json`，终端打印汇总表格。

### `micro-eval report`

从 run JSON 生成静态 HTML 对比报告。

```bash
micro-eval report <run-file> [OPTIONS]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `-o, --output` | `<run-file>.html` | 输出 HTML 路径 |

### `micro-eval ui`

启动本地 Next.js Web UI。

```bash
micro-eval ui [OPTIONS]
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--port` | `3000` | UI 服务端口 |

## eval.yaml 配置参考

```yaml
# 项目名称
project_name: my-agent-eval

# 全局超时（秒），可被 agent 级别覆盖
timeout_s: 120

# Baseline agent 配置
baseline:
  name: gpt-4o-baseline          # 显示名称
  command: "python agents/b.py"  # 执行命令
  input_mode: stdin              # stdin | file
  output_mode: stdout            # stdout | file | directory
  timeout_s: 60                  # 单任务超时
  env:                           # 环境变量
    MODEL: gpt-4o

# Candidate agent 配置（字段同 baseline）
candidate:
  name: claude-candidate
  command: "python agents/c.py"
  input_mode: stdin
  output_mode: stdout
  timeout_s: 60
  env:
    MODEL: claude-sonnet

# 任务文件目录（相对于 eval.yaml）
tasks_dir: tasks

# 结果输出目录
output_dir: .micro-eval/runs

# 是否并行执行
parallel: true
```

### Agent 配置字段详解

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | string | 必填 | agent 显示名称 |
| `command` | string | 必填 | 执行命令，支持 `{input_file}` 和 `{output_dir}` 模板变量 |
| `input_mode` | enum | `stdin` | `stdin`：通过标准输入传递；`file`：写入临时文件，路径通过 `{input_file}` 注入 |
| `output_mode` | enum | `stdout` | `stdout`：从标准输出收集；`file`：从 `{output_dir}` 读取第一个文件 |
| `timeout_s` | float | `300.0` | 单任务超时秒数 |
| `env` | map | `{}` | 传递给子进程的环境变量 |

## Task YAML 格式

每个任务是 `tasks/` 目录下的一个 `.yaml` 文件：

```yaml
id: summarize-001              # 唯一标识（默认取文件名）
name: 文章摘要测试
description: 测试 agent 对长文的摘要能力
input_payload: |
  请对以下文章生成 100 字摘要：
  ...（文章内容）...
expected_output: null          # 可选，设置后用于自动评分
rubric: |                      # 人工评分标准
  - 摘要长度 80-120 字
  - 覆盖主要论点
  - 无事实错误
business_impact_tier: 2        # 1=关键 2=重要 3=一般
tags: [summarization, chinese]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 否 | 唯一标识，默认取文件名 |
| `name` | string | 否 | 任务显示名称 |
| `description` | string | 否 | 任务描述 |
| `input_payload` | string | 是 | 传递给 agent 的输入内容 |
| `expected_output` | string | 否 | 期望输出，用于自动评分 |
| `rubric` | string | 否 | 人工评分标准 |
| `business_impact_tier` | int | 否 | 业务影响等级 1-3 |
| `tags` | list | 否 | 标签列表 |

## Web UI

本地 Web UI 基于 Next.js，直接读取 `.micro-eval/runs/` 目录下的 JSON 文件。

```bash
# 启动方式一：通过 CLI
micro-eval ui --port 3000

# 启动方式二：直接运行
cd ui && npm run dev
```

功能：
- **Run 列表** — 按时间排序浏览所有评测记录
- **对比表格** — 每个 task 的 baseline vs candidate 结果并排展示
- **状态高亮** — pass/fail/error/timeout 颜色区分

UI 通过环境变量 `MICRO_EVAL_PROJECT_ROOT` 指定项目根目录（默认为 `ui/` 的上级目录）。

## 架构概览

```
┌─────────────────────────────────────────────────┐
│  CLI (Typer)                                    │
│  micro-eval run / report / ui                   │
├─────────────────────────────────────────────────┤
│  Config Loader          │  Scorer (DeepEval)    │
│  eval.yaml + tasks/*.yaml│  精确匹配 / 自定义   │
├─────────────────────────────────────────────────┤
│  Execution Engine (asyncio)                     │
│  AgentRunner → subprocess → collect output      │
├─────────────────────────────────────────────────┤
│  Workspace Manager (git worktree)               │
│  隔离执行环境，保证可复现                         │
├─────────────────────────────────────────────────┤
│  Data Layer (Pydantic models → JSON files)      │
│  .micro-eval/runs/*.json                        │
└─────────────────────────────────────────────────┘
         ↕
┌─────────────────────────────────────────────────┐
│  Web UI (Next.js + React + Tailwind)            │
│  读取 .micro-eval/runs/ 展示对比结果             │
└─────────────────────────────────────────────────┘
```

## 路线图

### Phase 1（MVP）— 当前

- [x] 项目/任务/运行核心模型
- [x] 自写执行层（asyncio 并行）
- [x] 精确匹配评分
- [x] 基础对比页（Web UI）
- [x] 静态 HTML 报告
- [x] CLI（run / report / ui）

### Phase 2 — 观测与复盘

- [ ] Langfuse trace 接入
- [ ] 复盘页（trace 回放）
- [ ] 成本分析（cost_usd 聚合）
- [ ] Skill profile 对比

### Phase 3 — 沙箱与高级任务

- [ ] OpenHands sandbox 接入
- [ ] 复杂任务类型（多步骤、工具调用）
- [ ] 趋势分析（跨 run 对比）

## 许可证

待定




