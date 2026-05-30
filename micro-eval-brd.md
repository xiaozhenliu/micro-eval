# BRD: AI 小团队的 Agent 评测决策工具

**项目代号**: `micro-eval`
**文档类型**: Business Requirement Document(商业需求文档)
**版本**: V2
**日期**: 2026-05-30
**状态**: Approved (CEO Review)
**关联文档**: 产品规格详见 `micro-eval-prd.md`，设计文档详见 `~/.gstack/projects/micro-eval/xz-main-design-*.md`

**一句话**: 一个 CLI + 本地 Web UI 的评测工具，让 agent 开发者能快速回答"这次改动到底是变好了还是变差了"。

---

## 1. 背景

AI 小团队在迭代 agent/skill/prompt 时，缺乏一个轻量的方式来回答"这次改动到底是变好了还是变差了"。当前的做法是手动测试、截图、凭感觉判断，没有系统化的对比流程。

现有问题不是"没有工具"（10+ 竞品存在），而是：

- 现有评测工具面向 LLM API 调用，不面向完整 agent 程序
- agent 执行时间长（分钟级），现有工具假设毫秒级响应
- agent 产出是代码/文件变更，不只是文本输出
- 团队需要的是"决策信心"，不是更多 metrics

---

## 2. 核心痛点

### 2.1 没有 agent 级别的对比工具

现有评测工具（Promptfoo、DeepEval 等）的核心用例是 LLM prompt 对比。但 agent 开发者对比的是完整程序：Claude Code CLI、LangGraph workflow、自定义 agent 脚本。这些通过 shell command 调用，执行时间长，产出复杂。

### 2.2 结果不可积累

每次对比都是一次性的。团队无法回答"上一次改动的效果到底如何"，无法看到迭代趋势。

### 2.3 决策缺乏数据支撑

"感觉更好了"不是决策依据。团队需要 pass rate、cost、latency 的量化对比来做决策。

---

## 3. 目标用户

### 3.1 核心用户（MVP）

**创始人自己** — 一个 agent 开发者，频繁迭代 prompt/skill/agent 组合。

### 3.2 验证目标

找 5-10 个类似的 agent 开发者验证需求（Codex 的挑战，已接受）。

### 3.3 后续用户

- 2-20 人 AI 小团队
- 独立 agent 开发者
- 以 agent/workflow 为核心的创业团队

---

## 4. 业务目标

1. 创始人自己每周使用 micro-eval 做至少 2 次 agent 对比
2. 从"改→试→看→判断"的循环时间降到可量化（<10 min per comparison）
3. 5 个 agent 开发者中至少 3 个认可这个 workflow

---

## 5. 产品定位与边界

### 5.1 定位

CLI + 本地 Web UI 的 **Agent 评测决策工具**。

不是评测平台，不是 observability 工具，不是 benchmark suite——就是一个"改了之后到底好没好"的快速回答器。

### 5.2 做什么

- 接受 agent 配置（shell command 形式），在同一组任务上运行
- 生成决策报告：哪个更好、好在哪、成本差多少
- 本地 Web UI 查看对比结果、标注评分
- 环境快照保证结果可复现

### 5.3 不做什么

- 不自研评测引擎底座（用 DeepEval）
- 不做多人协作 / RBAC / SSO
- 不做 hosted service（纯本地工具）
- 不做 observability（用 Langfuse）
- 不做 sandbox（用户自己管理 agent 执行环境）

---

## 6. 被评测对象

micro-eval 评测的是**完整 agent 程序**，不是 LLM prompt 模板。

被评测对象通过 shell command 调用，包括：
- **CLI agent** — Claude Code 非交互模式（`claude -p "..." --output-file ...`）
- **LangGraph workflow** — 用 LangGraph 编排的 agent 工作流（`python my_graph.py --task "..."`）
- **任何其他 agent** — CrewAI、AutoGen、自定义脚本等

关键特征：
- 执行时间长（分钟级，不是毫秒级）
- 产出复杂（代码变更、文件输出，不只是文本）
- 需要隔离环境（每个 agent 跑在独立工作目录）

---

## 7. 技术方案

### 7.1 架构

- **Python CLI**（Typer）— 评测执行，通过 DeepEval 自定义 metric 调用 agent
- **Next.js UI**（TypeScript）— 本地 Web UI，API routes 读取 `.micro-eval/` 数据
- **DeepEval** — Python 原生评测框架，自定义 metric 调用 agent subprocess
- **Langfuse**（可选）— cost/latency 数据补充

### 7.2 为什么用 DeepEval 而不是 Promptfoo

- DeepEval 是 Python 原生，直接 import，不需要 Node.js runtime
- Promptfoo 已被 OpenAI 收购，有结构性风险
- DeepEval 的自定义 metric 比 Promptfoo 的 custom script provider 更适合评测完整 agent
- 消除跨语言 subprocess 的复杂度

---

## 8. 商业模式

### 8.1 当前阶段

开源 CLI 工具，npm/pip 包分发。先验证需求，后考虑商业化。

### 8.2 未来可能

- Team 版（共享评测结果、协作标注）
- Hosted reports（在线分享报告）
- 付费 LLM-as-judge（使用 micro-eval 的评判模型）

---

## 9. 业务风险

### 9.1 胶水层可持续性

如果 DeepEval/Langfuse 各自补齐功能，micro-eval 的差异化必须从"连接"转向"决策工作流"。

**缓解**：EvalEngine 适配层隔离底座变化；核心价值定位在"决策"而非"评测"。

### 9.2 需求未验证

创始人自己做用户，但外部需求尚未验证。

**缓解**：48 小时原型 → 自用一周 → 找 5 个 agent 开发者验证。

### 9.3 竞争激烈

10+ 竞品存在（Braintrust、Patronus、Ragas 等）。

**缓解**：瞄准"完整 agent 程序评测"这个 niche，不是"LLM prompt 评测"。

---

## 10. 成功标准

1. 创始人每周使用 ≥2 次
2. 单次对比 <10 分钟完成
3. 5 个 agent 开发者中 ≥3 个认可 workflow
4. 能清晰回答"这次改动好没好"
