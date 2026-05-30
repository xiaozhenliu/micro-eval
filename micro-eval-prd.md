# PRD: AI Agent 评测决策工具

**项目代号**: `micro-eval`
**文档类型**: Product Requirement Document(产品需求文档)
**版本**: V2
**日期**: 2026-05-30
**状态**: Approved (CEO Review)
**关联文档**: 商业背景详见 `micro-eval-brd.md`，设计文档详见 `~/.gstack/projects/micro-eval/`

---

## 1. 产品概述

### 1.1 核心目标

让 agent 开发者能快速回答"这次改动到底是变好了还是变差了"。

具体：
1. 接受两个 agent 配置（baseline vs candidate），在同一组任务上运行
2. 生成量化对比：pass rate、cost、latency
3. 提供决策报告：哪个更好、好在哪、值不值得继续

### 1.2 成功定义

用户可以在 10 分钟内完成：
- 配置两个 agent（shell command 形式）
- 定义一组评测任务
- 发起一次 run
- 在本地 Web UI 中查看对比结果
- 得到清晰结论："candidate 在 X 上更好，cost 增加 Y%，值得继续"

---

## 2. 被评测对象

**完整 agent 程序**，通过 shell command 调用。不是 LLM prompt 模板。

支持的 agent 类型：
- **CLI agent** — Claude Code 非交互模式（`claude -p "..." --output-file ...`）
- **LangGraph workflow** — 用 LangGraph 编排的 agent 工作流（`python my_graph.py --task "..."`）
- **任何其他 agent** — CrewAI、AutoGen、自定义脚本等

关键特征：
- 执行时间长（分钟级，不是毫秒级）
- 产出复杂（代码变更、文件输出，不只是文本）
- 需要隔离环境（每个 agent 跑在独立工作目录）

---

## 3. 产品结构

### 3.1 CLI 层（Python / Typer）

```
micro-eval init                                     # 生成 eval.yaml + tasks/
micro-eval run --baseline <name> --candidate <name> # 运行对比
micro-eval report [--run <id>]                      # 生成 HTML 决策报告
micro-eval ui                                       # 启动本地 Web UI
micro-eval doctor                                   # 检查环境依赖
```

### 3.2 评测引擎层（DeepEval）

通过 DeepEval 自定义 metric 调用 agent subprocess：

```python
from deepeval.metrics import BaseMetric

class AgentEvalMetric(BaseMetric):
    def measure(self, test_case):
        result = subprocess.run(
            agent_command, capture_output=True, timeout=self.timeout
        )
        self.score = self.judge(result, test_case.expected_output)
        self.success = self.score >= self.threshold
```

### 3.3 展示层（Next.js + TypeScript）

本地 Web UI，通过 API routes 读取 `.micro-eval/` 数据：
- Run 列表页 — 所有历史 run
- 对比页 — baseline vs candidate 并排对比
- 标注页 — 人工评分和备注
- 报告页 — 决策报告展示

---

## 4. 产品原则

### P1. 决策优先
产品的核心输出是"决策信心"，不是更多 metrics。

### P2. Agent-Native
面向完整 agent 程序（分钟级执行、复杂产出），不是 LLM API 调用。

### P3. 同起点优先
所有 run 必须明确起点（环境快照），避免环境噪声。

### P4. 可解释优先
任何结论都要能回到任务、输出、diff、cost。

### P5. 先人工后自动
MVP 阶段人工评分优先，自动评分（LLM-as-judge）逐步增强。

---

## 5. 核心对象定义

### 5.1 Project

一个 eval.yaml 文件 = 一个项目。

字段：name, description, agents (map), tasks_dir, langfuse (optional)

### 5.2 AgentConfig

一个 agent 配置 = 一个 shell command + 超时 + 输出模式。

```yaml
agents:
  claude-code:
    type: command
    run: "claude -p '{input}' --output-file {output_dir}/result.txt"
    timeout: 300
    output_mode: file
    workdir: "{workspace}"
  langgraph-v2:
    type: command
    run: "python agents/router_v2.py --task '{input}' --output-dir {output_dir}"
    timeout: 600
    output_mode: directory
    workdir: "{workspace}"
```

### 5.3 Task

一个 task = 一个可重复运行的测试单元。

```yaml
title: Fix login redirect bug
input_payload: |
  The login page redirects to /dashboard but should redirect to /home
expected_output: |
  auth.ts modified to redirect expired sessions to /home
rubric: "Correctly identifies the redirect target"
tags: [bug-fix, auth]
```

### 5.4 Run

一次 run = 对某个任务集的实际执行。

字段：id, timestamp, baseline_agent, candidate_agent, tasks, results[], environment_snapshot, schema_version

### 5.5 RunResult

一个 result = 一个 task × agent 的结果。

字段：task_id, agent_name, pass_fail, score, output_summary, cost, latency, failure_mode

---

## 6. 数据模型与文件结构

```
project-root/
  eval.yaml              # 项目配置
  tasks/
    task-001.yaml        # 单个 task
    task-002.yaml
  .micro-eval/
    runs/
      run-<timestamp>.json    # Run 元数据 + results 数组
    reports/
      run-<timestamp>.html    # 生成的 HTML 报告
```

Run JSON 包含 `schema_version: "1.0"` 字段，为未来迁移做准备。

---

## 7. 用户流程

### 7.1 首次使用

```
micro-eval init          → 生成 eval.yaml 模板 + tasks/ 目录
编辑 eval.yaml           → 配置 agent commands
编辑 tasks/*.yaml        → 定义评测任务
micro-eval doctor        → 检查环境
micro-eval run           → 执行评测
micro-eval ui            → 查看结果
```

### 7.2 日常迭代

```
修改 agent 代码/prompt
micro-eval run --baseline v1 --candidate v2
micro-eval ui            → 对比结果、标注评分
决策：继续 / 回滚 / 再改
```

---

## 8. 评分体系

### 8.1 技术侧（自动）
- DeepEval assertion pass/fail
- 输出是否符合 rubric
- 是否通过测试（如果 task 定义了测试命令）

### 8.2 成本侧（自动）
- token 消耗 + 估算 USD（从 Langfuse 获取，或 agent 自报告）
- 执行时间（latency）

### 8.3 过程侧（人工标注）
- 是否卡住 / 过度迭代
- 是否使用了有效工具
- 代码质量评分（1-10）

### 8.4 业务侧（人工标注）
- 任务重要级别
- 是否优于人工基线
- 是否值得继续投入

---

## 9. 与底座的分工

### 9.1 DeepEval
承担：评测编排、自定义 metric、assertion、LLM-as-judge（Phase 2）。
本产品利用它做"跑评测"的那层。

### 9.2 Langfuse（可选）
承担：trace、cost/latency 统计。
本产品利用它做"看成本"的那层。未配置时降级运行。

### 9.3 不用的底座
- **Promptfoo** — 已被 OpenAI 收购，且核心用例是 LLM prompt 对比，不适合 agent 评测
- **OpenHands** — sandbox 能力推迟到 Phase 3

---

## 10. MVP 范围（48 小时原型）

### 10.1 必做
- `micro-eval run` — 通过 DeepEval 执行 agent 对比
- `micro-eval report` — 生成静态 HTML 报告
- `micro-eval ui` — Next.js 本地 Web UI（run 列表 + 对比页）
- eval.yaml 配置加载
- Run JSON 写入

### 10.2 Day 3+ (nice-to-have)
- `micro-eval doctor` — 环境检查
- `micro-eval init` — 模板生成
- 环境快照记录
- Langfuse 集成
- YAML 校验和友好错误提示
- 人工标注功能

### 10.3 不做
- Web dashboard（hosted）
- Auth / teams / 多人协作
- 自动评分引擎（超出 DeepEval assertion）
- Fancy trace UI
- OpenHands sandbox 集成

---

## 11. 路线图

### Phase 1: MVP（48 小时）
- CLI: run, report, ui
- DeepEval 集成
- 基础对比页
- 静态 HTML 报告

### Phase 2: 可用版（2-4 周）
- Langfuse trace 接入
- LLM-as-judge（DeepEval GEval）
- 人工标注 + 持久化
- 成本分析
- diff 高亮

### Phase 3: 增强版（1-3 月）
- OpenHands sandbox 接入
- 多 agent 对比（>2）
- 结果趋势分析
- 团队协作功能
