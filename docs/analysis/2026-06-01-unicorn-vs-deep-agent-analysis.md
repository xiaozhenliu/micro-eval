---
title: "AWS Deep Agent Eval vs micro-eval 对比分析"
date: 2026-06-01
status: 分析完成
type: competitive-analysis
subject: aws-deep-agent-eval
scope: 架构、任务定义、执行、评分、观测、隔离、对比、安全、扩展、成熟度
tags:
  - competitive-analysis
  - agent-eval
  - architecture
---

# AWS Deep Agent Eval vs Unicorn (micro-eval) 对比分析

**日期**: 2026-06-01
**状态**: 分析完成
**方法**: 逐维度深度对比（架构、任务定义、执行、评分、观测、隔离、对比、安全、扩展、成熟度）

---

## 1. 项目概述

### AWS Deep Agent Evaluation

AWS 官方博客发布的 Agent 评测参考实现。技术栈为 pytest + LangSmith + deepagents 框架，以 SQL Agent（Chinook 数据库）为评测对象，演示离线评估的五种模式：确定性断言、LLM-as-judge、工具调用验证、轨迹分析、人工校准。

**定位**: 教学级 demo，约 500 行代码，可直接运行。

**核心流程**:
```
test function -> agent.invoke() -> extract results -> assert/grade -> log to LangSmith
```

### Unicorn (micro-eval)

面向 1-20 人 AI 小团队的 Agent/Skill 评测工作台。核心命题：将"我觉得这个 agent 更强"转化为可量化、可溯源、可复现的结论。

**定位**: 生产级评测平台，当前 v0.1.0 MVP（Python CLI + Next.js Web UI）。

**核心流程**:
```
Tasks × Configurations × Repetitions -> ResultMatrix -> 对比/溯源/报告
```

---

## 2. 架构对比矩阵

| 维度 | AWS Deep Agent Eval | Unicorn (micro-eval) | 优势方 |
|------|-------------------|---------------------|--------|
| **架构模型** | 线性管道（pytest = 运行器，每次执行 = 一次实验） | 矩阵模型（Run = Tasks x Configs x Reps，显式笛卡尔积） | micro-eval |
| **Task 定义** | 硬编码在 pytest 函数体内，无独立 schema | 结构化对象（input + expectations + workspace + rubric + tier） | micro-eval |
| **Agent 执行** | 进程内调用（LangChain agent.invoke()），框架耦合 | 黑盒 subprocess（stdin/文件传参），协议耦合 | micro-eval |
| **评分机制** | 三种混合（断言 + LLM judge + 人工校准），ad-hoc rubric | 三层递进（Validation → Grading → Annotation），结构化 rubric 框架 | micro-eval |
| **Trace/观测** | LangSmith 自动 tracing，零配置但锁定生态 | 多 provider 回退（Langfuse/LangSmith/self_report/builtin），非侵入式 | 各有优势 |
| **沙箱隔离** | 几乎没有（SQL readonly + pytest tmp_path） | 5 维模型，Level 0-4 渐进式隔离 | micro-eval |
| **多配置对比** | 不原生支持，需手动跑多次 + LangSmith UI 并排 | 核心设计目标，矩阵列 = 不同 Configuration | micro-eval |
| **安全模型** | 最小化（环境变量注入，无 redaction） | 完整 BYOK + redaction + proxy mode + OWASP 威胁建模 | micro-eval |
| **扩展性** | 无 plugin 系统，写新 pytest 函数 = 唯一扩展方式 | 多层 provider 协议 + entry points 注册 | micro-eval |
| **成熟度** | 小而完整的 demo，可直接运行 | 大而部分实现的平台，设计完成度高但实现在 Phase 1 | AWS（可运行性） |

---

## 3. AWS 项目的完备程度评估

### 3.1 已实现部分

**代码质量**: 清晰、可读、符合 Python 最佳实践。pytest fixture 组织合理，conftest.py 职责单一。

**覆盖的评估模式**:

1. **确定性断言** — `assert "8" in answer`，简单直接
2. **LLM-as-judge** — 结构化 rubric prompt，返回 JSON 评分（correctness/completeness/clarity 各 0.0-1.0）
3. **工具调用验证** — 检查 agent 是否调用了正确的工具及参数
4. **轨迹分析** — 验证推理步骤的合理性和效率
5. **人工校准** — 通过 LangSmith Align Evaluator 校准 LLM judge

**集成完整性**: LangSmith tracing 零配置自动工作，评分结果通过 `t.log_feedback()` 与 trace 关联，实验结果可在 LangSmith UI 中可视化对比。

**可运行性**: 配置 AWS 账号 + LangSmith API key 后即可 `pytest` 运行，无额外依赖。

### 3.2 缺失或简化之处

| 缺失项 | 影响 | 说明 |
|--------|------|------|
| 独立数据集管理 | 无法扩展到 50+ task | task 硬编码在函数体内 |
| 多 agent 对比 | 核心场景不支持 | 对比需改代码 + 跑两次 |
| Repetitions / pass@k | 结果统计不可靠 | 博客提到但代码未实现 |
| 沙箱隔离 | 安全风险 | 仅 SQL readonly，无系统级隔离 |
| 结构化 rubric | 评分不可复现 | rubric 是内联字符串，无版本管理 |
| 成本追踪 | 无法做 ROI 分析 | 依赖 LangSmith 平台能力 |
| 报告生成 | 无自动化产出 | 依赖 LangSmith UI 手动查看 |
| CI/CD 集成 | 无法自动化回归 | 纯手动触发 |

### 3.3 生产就绪度评估

**结论: 不适合生产使用。**

- 任务管理完全依赖代码修改，非工程师无法参与
- 无数据持久化层（每次运行是独立的 pytest session）
- 安全模型仅适用于 SQL-only 场景
- 对比能力依赖外部平台（LangSmith），非内建
- 无 CI/CD 集成设计

**适用场景**: 单人开发者快速验证单个 LangChain agent 的基本能力，作为开发阶段的冒烟测试。AWS 方案的价值在于"500 行代码就能跑起来"——这是一个有用的起点，但不是终点。

---

## 4. micro-eval 可借鉴之处

### 4.1 pytest 作为运行器骨架

**AWS 做法**: pytest 是唯一的运行器。测试发现、执行、报告、fixture 管理全部复用 pytest 生态。

```python
# AWS: 零额外框架，pytest 原生能力
@pytest.fixture
def sql_agent():
    return create_deep_agent(...)

def test_simple_query(sql_agent):
    result = sql_agent.invoke({"messages": [...]})
    assert "8" in result["messages"][-1].content
```

**借鉴建议**: micro-eval 不需要重写测试发现和执行调度。矩阵展开可以在 pytest 之上实现——通过 `pytest.mark.parametrize` 或自定义 plugin 生成笛卡尔积。这样既保留了矩阵模型的表达力，又复用了 pytest 的并行执行（pytest-xdist）、报告、CI 集成等成熟能力。

**优先级**: 中。当前自写调度器已经工作，但长期维护成本高于 pytest plugin 方案。

### 4.2 pass@k / pass^k 统计指标

**AWS 做法**: 博客中提到 pass@k（k 次中至少一次通过的概率）作为评估指标，虽然代码未实现。

**借鉴建议**: micro-eval 已有 repetitions 维度，应为其定义标准聚合方式：
- `pass@k`: P(至少 1 次通过 | k 次尝试) — 衡量 agent 的"能力上限"
- `pass^k`: P(全部通过 | k 次尝试) — 衡量 agent 的"可靠性下限"
- `consistency`: std(scores) across repetitions — 衡量稳定性

这三个指标应作为 ResultMatrix 的内建聚合函数，在对比页中默认展示。

**优先级**: 高。直接影响结果可信度的呈现方式。

### 4.3 在线评估模式

**AWS 做法**: 博客描述了对生产 trace 的实时评分——agent 在生产环境处理真实请求时，LangSmith 自动采集 trace 并触发评分。

**借鉴建议**: micro-eval 当前只有离线评估（手动触发 Run）。可在 Phase 2+ 规划"监控模式"：
- 监听 Langfuse/LangSmith 的新 trace
- 对满足条件的 trace 自动触发评分
- 生成趋势报告（"本周 agent 质量是否退化？"）

这对持续质量保证有重要价值，但不应阻塞 MVP。

**优先级**: 低（Phase 2+）。

### 4.4 "能用断言就不用 LLM"原则

**AWS 做法**: 评分优先级明确——能用 `assert` 解决的绝不用 LLM judge。LLM judge 只用于无法确定性验证的维度（如"回答是否清晰"）。

```python
# AWS: 确定性优先
assert "8" in answer  # 先用断言
# 只有断言不够时才用 LLM judge
scores = llm_judge(answer, rubric)
```

**借鉴建议**: micro-eval 的 Layer 1 Validation（exit code 验证）已体现这个思路，但应更激进地扩展：
- 对 coding task：运行测试套件 > LLM 评分
- 对 SQL task：执行查询对比结果集 > LLM 评分
- 对 API task：schema 验证 + 状态码检查 > LLM 评分

原则：**每增加一个确定性检查，就减少一次 LLM judge 调用（省钱 + 更可靠）**。

**优先级**: 高。直接影响评分成本和可靠性。

### 4.5 Skills 作为 Markdown 文件

**AWS 做法**: deepagents 框架中 Skill 定义为 `SKILL.md`，包含 YAML frontmatter（元数据）+ Markdown body（工作流步骤）。非工程师可直接编辑。

**借鉴建议**: micro-eval 的 Skill 概念已存在，但配置格式未最终确定。参考 AWS 的 frontmatter + workflow steps 格式：

```markdown
---
name: code-review
version: 2.1.0
model: claude-sonnet-4
tools: [read_file, search, write_file]
temperature: 0.3
---

## Steps
1. Read the diff
2. Identify issues by category
3. Output structured review
```

这种格式兼顾了机器可解析和人类可编辑。

**优先级**: 中。影响用户体验但不阻塞核心功能。

---

## 5. micro-eval 的优势

### 5.1 多配置对比（核心差异化）

micro-eval 的矩阵模型是产品存在的理由。AWS 方案要对比两个 agent 需要：修改代码 -> 跑两次 pytest -> 在 LangSmith UI 手动并排。micro-eval 只需在 Configuration 列表中多加一项，Run 自动展开笛卡尔积。

**具体优势**:
- 声明式矩阵定义，自动展开
- baseline/candidate 并行执行
- ResultMatrix 天然支持多维度交叉分析
- blind comparison（A/B 匿名化）消除评分偏见

这不是"功能更多"，而是**产品模型根本不同**。

### 5.2 黑盒 Agent 协议

AWS 方案锁死在 LangChain 生态——只能评估通过 `agent.invoke()` 调用的进程内对象。micro-eval 的黑盒协议（stdin/stdout + 环境变量）可以评估：

- Claude Code、Cursor、Copilot（CLI 模式）
- Docker 容器中的任意 agent
- 远程 API（通过 wrapper script）
- 人类操作员（通过 UI 录入结果）
- 未来任何新框架的 agent

这是 micro-eval 的根本性架构优势——不与任何框架耦合。

### 5.3 沙箱隔离体系

AWS 的"隔离"仅限于 SQLite readonly mode。对于运行任意代码的 agent 评测场景，这完全不可接受。

micro-eval 的 5 维沙箱模型提供了：
- **渐进式隔离**: Level 0 (git worktree) 到 Level 4 (Firecracker VM)，按风险选择
- **多轴约束**: filesystem / network / process / resources 独立控制
- **信任分级**: trusted -> semi_trusted -> untrusted -> adversarial
- **统一接口**: WorkspaceProvider 协议，切换隔离级别不改业务代码

对于评测第三方/未知 agent 的场景，这是必需的安全基础设施。

### 5.4 评分系统深度

| 能力 | AWS | micro-eval |
|------|-----|---------|
| 确定性断言 | 有 | 有（Layer 1 Validation） |
| LLM-as-judge | 有（单 judge，内联 rubric） | 有（多 judge，结构化 rubric） |
| 多轴评分 | 无 | 有（按任务类型自动选择模板） |
| Trajectory evaluation | 无 | 有（tool_efficiency/reasoning_quality/resource_usage） |
| Blind comparison | 无 | 有（A/B 匿名化） |
| 多 judge 共识 | 无 | 有（2/3 agreement） |
| 人工标注 UI | 依赖 LangSmith | 内建 Web UI |
| Rubric 版本管理 | 无 | 有 |

特别是 **trajectory evaluation**（不只看结果，还看过程）是 micro-eval 的差异化能力。两个 agent 可能都通过了 task，但一个用了 3 步 $0.03，另一个用了 30 步 $0.30——这个差异只有通过轨迹评估才能发现。

### 5.5 安全模型

AWS 假设可信环境（你自己的 AWS 账号、你自己的 agent）。micro-eval 假设半可信/不可信环境，提供：

- **Secrets 隔离**: per-Configuration key override，proxy mode（secrets 不进沙箱）
- **输出 Redaction**: 正则模式匹配（sk-ant-*, sk-*, ghp-*），防止 agent 泄露 key
- **OWASP 威胁建模**: 基于 Agentic/LLM 框架识别 top 5 风险
- **成本熔断**: circuit breaker 防止失控 agent 消耗无限资源

对于多人团队评测第三方 agent 的场景，这些是生产级必需品。

---

## 6. 结论

AWS Deep Agent Eval 和 micro-eval 不在同一个层面上竞争。AWS 是一个精心设计的教学 demo，证明了"pytest + LangSmith 就能做 agent 评测"；micro-eval 是一个生产级评测平台的完整设计，解决的是"多 agent 对比 + 可复现 + 可溯源"的系统性问题。

**两者的关系不是替代，而是互补**：
- AWS 验证了"最小可行评测"的形态——这是 micro-eval Phase 1 应该达到的体验标准
- micro-eval 的设计深度解决了 AWS 方案在扩展时必然遇到的问题

**关键判断**：

1. **micro-eval 的架构方向正确**。矩阵模型、黑盒协议、分层评分、渐进式隔离——这些设计决策经得起与工业级方案的对比。

2. **最大风险不是设计不足，而是实现过慢**。micro-eval 的设计广度远超 AWS，但 AWS 500 行代码已经能跑。

3. **从 AWS 借鉴的核心不是技术，而是态度**："先跑起来再说"。一个能跑的 MVP 比一份完美的设计文档更有价值。

---

## 借鉴建议的采纳核查（2026-06-02）

> 对照 `2026-06-02-unicorn-design.md`，逐条核查 §4 五条借鉴建议的落地情况；未采纳 / 降级项给出合理性判断。

| 建议 | 原优先级 | 设计文档落地 | 判断 |
|------|---------|------------|------|
| 4.1 pytest 作为运行器骨架 | 中 | **未采纳**。Execution Kernel 用自写 asyncio subprocess（§5.1/§5.3），未走 pytest plugin / pytest-xdist | 合理：CLAUDE.md 已锁定"自写执行层"（工程评审决策）；矩阵模型 `Task×Config×Rep` + 黑盒 subprocess adapter 与 pytest 的 test-function 范式不同，强行套 pytest 反增耦合 |
| 4.2 pass@k / pass^k | 高 | **降级**。pass@k/pass^k 被放在 Evaluation Layer 的 **Future/L2**（§5.7、§8），未进 MVP 默认展示 | 基本合理但偏保守：MVP `repetitions` 默认 =1，此时 pass@k ≡ pass rate，差异化价值需 rep>1 才显现；MVP 的 Basic Honest Stats（pass rate + consistency + 低样本警告）已覆盖最小需求。**建议**：rep>1 成为常态后应把 pass@k/pass^k 提升为对比页默认指标（计算成本 <10 行，矩阵已存全部 rep 结果）|
| 4.3 在线评估 / 监控模式 | 低 | **未采纳**，设计文档无相关内容 | 合理且一致：与 [[2026-06-01-unicorn-vs-brd-research]] §3.6 反目标"不做通用 observability 平台"对齐，属 Phase 2+ |
| 4.4 能用断言就不用 LLM | 高 | **完全采纳**：升为架构不变量 #6"Deterministic checks before LLM judgment"（§2），并贯穿 §4.1 | — |
| 4.5 Skill 作为 Markdown（frontmatter+steps） | 中 | **部分采纳**：用了 SKILL.md（§7.1）、skill_version 来自 frontmatter（§4），但 AWS 示例的 rich frontmatter（model/tools/temperature）未在 schema 中固化 | 合理：MVP 把 skill 建模为 path+version 足够；rich frontmatter 是后续 Asset Layer 细节 |

**小结**：5 条中 1 条完全采纳、1 条部分采纳、1 条合理降级、2 条合理未采纳。无"声称采纳实则缺失"的情况；唯一值得跟踪的是 4.2 pass@k 的降级——它在 rep>1 时应回到默认展示。
