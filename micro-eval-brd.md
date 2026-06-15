# BRD: AI 小团队的 Agent 评测决策工具

**项目代号**: `micro-eval`
**文档类型**: Business Requirement Document(商业需求文档)
**版本**: V3
**日期**: 2026-06-01
**状态**: Approved
**关联文档**: 设计规格详见 `docs/superpowers/specs/2026-06-02-unicorn-design.md`

**一句话**: CLI + 本地 Web UI 的评测工具，让 agent 开发者通过可量化、可溯源、可复现的对比回答"这次改动到底是变好了还是变差了"。

---

## 1. 背景

AI 小团队在迭代 agent/skill/prompt 时，缺乏一个轻量的方式来回答"这次改动到底是变好了还是变差了"。当前的做法是手动测试、截图、凭感觉判断，没有系统化的对比流程。

现有问题不是"没有工具"（10+ 竞品存在），而是：

- 现有评测工具面向 LLM API 调用，不面向完整 agent 程序
- agent 执行时间长（分钟级），现有工具假设毫秒级响应
- agent 产出是代码/文件变更，不只是文本输出
- 团队需要的是"决策信心"，不是更多 metrics
- 单次执行结果不可靠——agent 有内在随机性，需要多次重复才能得出可信结论

---

## 2. 核心痛点

### 2.1 没有 agent 级别的矩阵对比工具

现有评测工具的核心模型是"单输入单输出"。但 agent 开发者需要对比的是多维度组合：不同 agent × 不同 skill 版本 × 不同执行环境 × 不同参数。这是一个矩阵问题，不是二元对比。

### 2.2 评分方法与 agent 产出不匹配

Agent 产出是代码变更、文件修改、环境状态——不是可以 exact match 的文本。同一个 bug 有 10 种正确修法。需要分层评分：能用测试验证的先跑测试，无法确定性验证的才用 LLM 判断。

### 2.3 结果不可积累，不可复现

每次对比都是一次性的。agent 有内在随机性，单次执行可能误导决策。团队需要多次重复 + 统计聚合才能得出可信结论。

### 2.4 无法回答"为什么"

只知道"A 比 B 好"不够。需要知道：好在哪个维度？A 花了多少 token？B 在哪一步走偏了？没有执行轨迹采集，就无法做根因分析。

---

## 3. 目标用户

### 3.1 核心用户

1-20 人 AI 小团队中的 agent 开发者，频繁迭代 prompt/skill/agent 组合。

### 3.2 验证目标

找 5-10 个类似的 agent 开发者验证需求。

### 3.3 后续用户

- 独立 agent 开发者
- 以 agent/workflow 为核心的创业团队
- 企业内部 AI 工程团队

---

## 4. 业务目标

1. 创始人自己每周使用 micro-eval 做至少 2 次 agent 对比
2. 从"改→试→看→判断"的循环时间降到可量化（<10 min per comparison）
3. 5 个 agent 开发者中至少 3 个认可这个 workflow
4. 对比结论可复现——同样的配置重跑，结论一致

---

## 5. 产品定位与边界

### 5.1 定位

CLI + 本地 Web UI 的 **Agent 评测决策工具**。

核心命题：将"我觉得这个 agent 更强"转化为可量化、可溯源、可复现的结论。

### 5.2 做什么

- 接受多个 agent 配置（shell command 形式），在同一组任务上运行矩阵对比
- 分层评分：确定性验证（测试/lint/build）→ LLM-as-judge → 人工标注
- 多次重复执行 + 统计聚合，产出可信结论
- 采集执行轨迹（tool calls、token 消耗、延迟），支持根因分析
- 本地 Web UI 查看对比结果、标注评分、查看趋势
- 环境隔离保证结果可复现，防止 agent 间互相污染

### 5.3 不做什么

- 不做通用 observability 平台（聚焦评测场景的 trace 采集）
- 不做 benchmark suite（不维护公共题库，用户自定义 task）
- 不做企业级权限管理（MVP 阶段不做 RBAC / SSO，但团队共享评测结果是核心场景）

---

## 6. 被评测对象

micro-eval 评测的是**完整 agent 程序**和**独立 Skill**。

### 6.1 Agent 评测

被评测 agent 通过 shell command 调用，包括：
- **CLI agent** — Claude Code 非交互模式、Codex CLI、Cursor agent mode
- **LangGraph workflow** — 用 LangGraph 编排的 agent 工作流
- **任何其他 agent** — CrewAI、AutoGen、OpenHands、自定义脚本

### 6.2 Skill 评测

Skill 是 agent 的能力单元（一段 prompt + 工具集 + 工作流定义）。micro-eval 将 Skill 视为一等公民：

**独立评测**：直接测试 Skill 本身的质量，不依赖特定 agent 实现。
- 将 Skill 挂载到标准 host agent 上执行
- 对比同一 Skill 的不同版本（prompt 迭代、工具集变更）
- 对比不同 Skill 解决同一类任务的效果

**集成评测**：测试 Skill 在特定 agent 上的表现。
- 同一 agent + 不同 Skill 版本 → Skill 迭代效果
- 同一 Skill + 不同 agent → Skill 的可移植性
- 不同 agent × 不同 Skill → 最优组合发现

**典型场景**：
- "code-review skill v2 比 v1 好吗？" → 独立评测，固定 host agent
- "这个 skill 在 Claude Code 上比在 Cursor 上好吗？" → 集成评测，固定 Skill 变 agent
- "前端设计 skill 的新 prompt 改进了吗？" → 独立评测，对比版本

### 6.3 共同特征

无论评测 Agent 还是 Skill，被评测对象都具有：
- 执行时间长（分钟级，不是毫秒级）
- 产出复杂（代码变更、文件输出，不只是文本）
- 需要隔离环境（每个执行在独立 workspace）
- 有内在随机性（需要多次重复才能得出可信结论）

---

## 7. 核心概念

### 7.1 数据模型

```
Run = Tasks × Configurations × Repetitions → ResultMatrix
```

- **Task**: 一个评测任务（input + workspace + expectations + rubric）
- **Configuration**: 一个完整的被评测实体（Agent × Skill × Environment × Params）
- **Repetition**: 同一 (Task, Configuration) 的多次执行（观察方差）
- **ResultMatrix**: 所有结果的 N 维矩阵，支持多维度交叉分析

### 7.2 评分系统

五模式评分光谱，从确定性到主观性全覆盖：

| 模式 | 方法 | 成本 | 适用场景 |
|------|------|------|---------|
| Mode 1 | 确定性断言（test/lint/build） | ~$0 | 有明确对错的任务 |
| Mode 2 | 锚定式 Rubric（等级描述 + LLM） | $0.01-0.10 | 有标准但需判断的任务 |
| Mode 3 | 校准式 Rubric（专家校准 + LLM） | $0.05-0.20 | 主观但可对齐的任务 |
| Mode 4 | Pairwise Comparison（盲评 A/B → Elo） | $0.10-0.50 | 无法绝对评分的任务 |
| Mode 5 | 人工判断 | $5-50 | 自动化不可靠的任务 |

核心原则：**能用确定性验证的绝不用 LLM，LLM 仅处理代码无法覆盖的主观维度。**

### 7.3 执行隔离

每个 (Task, Configuration) 在独立 workspace 中运行。渐进式隔离：
- Level 0: git worktree（文件系统隔离）
- Level 1: 进程沙箱（macOS seatbelt / Linux bubblewrap）
- Level 2: Docker 容器（完整隔离）

### 7.4 可观测性

采集执行轨迹用于根因分析：
- tool calls 序列
- token 消耗 / 成本
- 延迟分布
- 错误恢复行为

通过 TraceProvider 接口对接 Langfuse/LangSmith/内建采集。

---

## 8. 技术方案

### 8.1 架构

- **Python CLI**（Typer）— 评测执行、矩阵展开、结果聚合
- **Next.js UI**（TypeScript）— 本地 Web UI，对比可视化、人工标注
- **评分引擎** — 分层 Verifier Pipeline（确定性验证器 + LLM judge）
- **Workspace Provider** — 可插拔的执行环境管理（worktree / docker）
- **Trace Provider** — 可插拔的轨迹采集（Langfuse / LangSmith / builtin）

### 8.2 技术栈

- Python 3.11+ / asyncio / Pydantic
- Next.js 15 / TypeScript / Tailwind
- SQLite（本地结果存储）
- git worktree（默认隔离）

---

## 9. 商业模式

### 9.1 当前阶段

开源 CLI 工具，pip 包分发。先验证需求，后考虑商业化。

### 9.2 未来可能

- Team 版（共享评测结果、协作标注）
- Hosted reports（在线分享报告）
- 付费 LLM-as-judge（使用 micro-eval 的评判模型）

---

## 10. 业务风险

### 10.1 评分可信度

如果评分系统不可靠（LLM judge 被操纵、确定性验证覆盖不足），用户不会信任结论。

**缓解**：确定性验证优先 + 多 judge 集成 + 锚定任务校准。

### 10.2 成本控制

矩阵展开 + 多次重复可能导致评测成本爆炸（50 task × 5 config × 8 reps = 2000 次执行）。

**缓解**：自适应验证路由（简单 case 只跑 Mode 1）+ 结果缓存 + 提前终止规则。

### 10.3 竞争激烈

10+ 竞品存在（Braintrust、Patronus、Ragas、Inspect AI 等）。

**缓解**：瞄准"完整 agent 程序的矩阵对比"这个 niche——不是 prompt 评测，不是 benchmark suite，是决策工具。

### 10.4 macOS 沙箱不确定性

sandbox-exec 已被 Apple 标记 DEPRECATED，可能在未来 macOS 版本中移除。

**缓解**：WorkspaceProvider 接口抽象隔离实现，可无缝切换到 Docker。

---

## 11. 成功标准

1. 创始人每周使用 ≥2 次
2. 单次矩阵对比 <15 分钟完成（含多次重复）
3. 5 个 agent 开发者中 ≥3 个认可 workflow
4. 能清晰回答"这次改动好没好"——附带维度分解和统计置信度
5. 对比结论可复现——同配置重跑，结论一致率 >90%
