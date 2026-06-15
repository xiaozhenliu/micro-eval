---
title: "micro-eval 设计文档策略：模块化 Unicorn 与 MVP Profile"
date: 2026-06-02
status: reference
type: strategy
source: "subagent draft based on product/architecture discussion"
tags:
  - design-strategy
  - modular-architecture
  - mvp
  - unicorn
---

# micro-eval 设计文档策略：模块化 Unicorn 与 MVP Profile

## 1. 背景与问题

当前 micro-eval 的设计文档面临两个相反但同时成立的风险。

第一，完整 Unicorn Design 仍然可能考虑不周。它需要覆盖长期架构、产品边界、执行层、评测层、可观测性、复现性、报告与决策链路。如果继续直接在一份完整设计里不断补充细节，很容易变成一个越来越大的混合文档：既想描述长期架构，又想指导 MVP 落地，还要记录研究判断和实现取舍。结果是文档变厚，但决策边界反而变模糊。

第二，单独新建一个独立 MVP 设计也有风险。MVP 如果脱离完整设计，会很容易为了短期实现方便而绕开关键抽象，例如绕过任务资产模型、跳过环境快照、把评分结果直接写死在 UI 结构里、或者让执行层和评测层耦合。这样短期能跑通，但后续接入 Langfuse、DeepEval、Docker sandbox、更多 agent adapter 或统计报告时，MVP 代码和数据模型都难以复用，甚至需要重写。

因此，真正的问题不是“继续完善完整设计”还是“另起 MVP 文档”二选一，而是要明确：

- 完整设计应该稳定什么；
- MVP 应该裁剪什么；
- 裁剪时哪些模块 contract 不能被绕过；
- 后续增强如何从 MVP 平滑升级，而不是推倒重来。

## 2. 核心结论

micro-eval 的文档体系应该分成四类角色：

1. **BRD = 用户和业务目标**

   BRD 负责说明 micro-eval 为什么存在、服务谁、解决什么业务问题、用户成功标准是什么。

   它回答：

   - 目标用户是谁；
   - 用户为什么需要 Agent / Skill 评测；
   - “可量化、可溯源、可复现”的商业价值是什么；
   - MVP 是否真正服务了核心使用场景。

2. **Research Doc = 取舍依据**

   Research Doc 负责记录关键技术与产品取舍的依据。

   它回答：

   - 为什么自写执行层，而不是直接使用完整评测框架；
   - 为什么 DeepEval 只作为评分库，而不是 test runner；
   - 为什么先人工评分，再逐步引入自动评分；
   - 为什么 MVP 先做本地执行和矩阵对比，而不是先做复杂协作、权限、推荐或大规模任务库。

3. **Unicorn Design = 模块化完整架构 + 长期不变量**

   Unicorn Design 不应该只是一个“超大版 PRD”或“远期功能清单”，而应该成为 micro-eval 的模块化完整架构文档。

   它负责定义长期稳定的模块、模块边界、核心数据模型、跨模块 contract、可复现性要求和证据链要求。

   它回答：

   - 系统由哪些稳定模块组成；
   - 每个模块的 responsibility 是什么；
   - 模块之间交换什么对象；
   - 哪些概念是长期不变量；
   - 哪些实现可以从 MVP 版本逐步升级。

4. **MVP Profile = 每个模块最低可用 maturity level 的组合**

   MVP 不是完整设计的 fork，而是 Unicorn Design 上的一个 Profile。

   它负责声明：在完整模块架构不变的前提下，每个模块在 MVP 阶段采用哪个最低可用 maturity level。

   它回答：

   - MVP 使用哪个 Agent Adapter 能力等级；
   - MVP 使用哪种 Workspace 隔离能力；
   - MVP 评分能力到人工评分、规则校验还是 LLM judge；
   - MVP trace 只保存本地 artifact，还是接入 Langfuse；
   - MVP 决策报告只做矩阵对比，还是做统计显著性和趋势分析。

核心判断是：

> 不要让 MVP 脱离完整设计，也不要让完整设计阻塞 MVP。  
> 先把完整 Unicorn Design 模块化，再把 MVP 写成 Unicorn Design 的一个 Profile。

## 3. 为什么不能只继续完善 Unicorn Design

只继续完善 Unicorn Design，会带来几个问题。

### 3.1 完整设计会无限膨胀

Unicorn Design 如果同时承担长期架构、MVP 实施、研究论证、路线图、UI 细节、底座接入计划，很快会变成一个大而全的文档。

这种文档的问题不是信息少，而是信息密度失控：

- 哪些是长期不变量，不清楚；
- 哪些只是当前 MVP 选择，不清楚；
- 哪些是未来可能实现，不清楚；
- 哪些必须现在遵守，不清楚。

对工程实现来说，模糊比缺失更危险。缺失可以补，模糊会导致不同人按不同理解实现。

### 3.2 完整设计容易阻塞 MVP

如果 Unicorn Design 每个模块都按最终形态设计，MVP 会被迫面对过多非必要问题：

- 是否马上接入 Langfuse；
- 是否马上做 Docker sandbox；
- 是否马上做自动评分；
- 是否马上做统计显著性；
- 是否马上做复杂报告；
- 是否马上支持多种 agent provider；
- 是否马上做任务库和版本管理。

这些能力长期重要，但不是 MVP 必须一次性完成。MVP 的目标是验证“配置 Configurations → 定义 Tasks → 发起 Run → 查看矩阵对比 → 得出结论”这条主链路，而不是实现完整平台。

### 3.3 完整设计无法表达“最低可用实现”

长期架构文档擅长定义模块和不变量，但不擅长表达“先做到哪个等级就够”。

例如 Evaluation Layer 的长期形态可能包括：

- deterministic validation；
- manual rubric scoring；
- DeepEval custom metric；
- GEval / LLM-as-judge；
- 多评委一致性；
- 统计校准；
- 结果解释与证据引用。

但 MVP 可能只需要：

- 运行结果收集；
- 基础 validation；
- 人工评分；
- 简单矩阵对比。

这些不是两个不同系统，而是同一个模块的不同 maturity level。这个概念必须从完整设计里拆出来，用 MVP Profile 明确选择。

## 4. 为什么不能只新建独立 MVP 文档

只新建一个独立 MVP 文档，也会带来严重问题。

### 4.1 MVP 容易变成架构 fork

如果 MVP 文档独立定义数据模型、执行流程、评分结构和 UI 结构，它很容易和 Unicorn Design 的长期模型分叉。

典型风险包括：

- MVP 用自己的 `task` 结构，后续无法对应完整 Task 模型；
- MVP 把 agent command 直接写进 run 逻辑，后续无法抽出 Agent Adapter；
- MVP 只保存最终分数，不保存 evidence，后续无法做可解释报告；
- MVP 不记录 workspace snapshot，后续无法比较结果是否可复现；
- MVP UI 直接消费临时 JSON，后续无法升级到稳定 ResultMatrix。

一旦这些结构进入代码，后续再“对齐完整设计”成本会很高。

### 4.2 MVP 会绕过真正重要的产品原则

micro-eval 的核心价值不是“能跑 agent”，而是帮助用户得到可信的评测结论。

可信结论依赖几个长期原则：

- 同起点优先；
- 可解释优先；
- 结果必须能回溯到 task、configuration、workspace、trace、artifact、score；
- 对比必须基于明确的 snapshot；
- 评分必须保留 rubric 和 evidence。

如果 MVP 独立设计，很容易把这些原则当成“以后再加”。但这些不是高级功能，而是 micro-eval 之所以成立的地基。

### 4.3 后续复用会变差

MVP 阶段如果不遵守模块 contract，后续每接一个能力都要改底层结构：

- 接 Langfuse 时发现没有 trace identity；
- 接 DeepEval 时发现评分结构不能表达 rubric 和 metric；
- 接 Docker 时发现 workspace 没有 snapshot contract；
- 做统计时发现 repetitions 和 configuration identity 不稳定；
- 做报告时发现 artifact 和 score 没有关联；
- 做任务库时发现 task 没有版本语义。

这不是“技术债”，而是产品模型没有稳定的问题。

因此，MVP 文档必须依附于 Unicorn Design，而不是另起炉灶。

## 5. 推荐文档架构

建议采用以下文档架构：

```text
micro-eval-brd.md
  |
  |-- 定义用户、业务目标、成功标准
  |
  v
Research Docs
  |
  |-- 记录关键取舍依据
  |-- 例如执行层自写、DeepEval 定位、Langfuse 定位、评分策略、同起点策略
  |
  v
2026-06-01-unicorn-design-v1.md
  |
  |-- 重构为 Modular Architecture
  |-- 定义长期不变量、稳定模块、跨模块 contract、核心数据模型
  |
  v
2026-06-02-mvp-profile.md
  |
  |-- 声明 MVP 在每个模块选择的 maturity level
  |-- 声明 MVP 不做什么
  |-- 声明哪些 contract 即使在 MVP 也必须遵守
```

推荐职责分工如下：

| 文档 | 主要职责 | 不应该承担 |
|---|---|---|
| BRD | 用户、业务目标、成功标准、市场与使用场景 | 具体技术实现细节 |
| Research Doc | 技术/产品取舍依据、外部方案比较、风险判断 | 作为最终架构 contract |
| Unicorn Design | 模块化完整架构、长期不变量、核心 contract | 把所有 MVP 实现细节混在主文里 |
| MVP Profile | MVP 选择的模块等级、范围、约束、落地路径 | 重新定义一套和 Unicorn 不兼容的模型 |

文档之间的关系应该是：

- BRD 决定“为什么做”；
- Research Doc 解释“为什么这样取舍”；
- Unicorn Design 定义“系统长期是什么”；
- MVP Profile 说明“现在先实现哪一层”。

## 6. 模块化 Unicorn 的模块图

```text
+-----------------------------+
|          BRD / Goals         |
|  users, problems, success    |
+--------------+--------------+
               |
               v
+-----------------------------+
|        Research Docs         |
|  tradeoffs, constraints      |
+--------------+--------------+
               |
               v
+=============================================================+
|                    Modular Unicorn Design                   |
|              stable modules and long-term contracts          |
+=============================================================+

+--------------------+        +-------------------------+
|    Asset Layer     | -----> |   Configuration Layer   |
| tasks, prompts,    |        | configs, repetitions,   |
| rubrics, skills    |        | matrix expansion        |
+---------+----------+        +-----------+-------------+
          |                               |
          |                               v
          |                    +-------------------------+
          |                    |    Execution Kernel     |
          |                    | run orchestration,      |
          |                    | timeout, concurrency    |
          |                    +------+-----------+------+
          |                           |           |
          |                           v           v
          |              +----------------+   +-----------------------------+
          |              | Agent Adapter  |   | Environment/Reproducibility |
          |              | command, I/O,  |   | workspace, snapshot,        |
          |              | skill mount    |   | setup, isolation            |
          |              +-------+--------+   +--------------+--------------+
          |                      |                           |
          |                      v                           v
          |              +------------------------------------------+
          |              |          Artifact / Trace Layer           |
          |              | stdout, stderr, files, diff, cost, trace  |
          |              +--------------------+---------------------+
          |                                   |
          |                                   v
          |              +------------------------------------------+
          |              |              Evaluation Layer             |
          |              | validation, manual score, rubric, judge   |
          |              +--------------------+---------------------+
          |                                   |
          |                                   v
          |              +------------------------------------------+
          |              |               Decision Layer              |
          |              | matrix, comparison, report, conclusion    |
          |              +------------------------------------------+

+=============================================================+
|                         MVP Profile                         |
|        selected maturity level for each Unicorn module       |
+=============================================================+
```

这张图表达两个关键点：

1. Unicorn Design 的模块是长期稳定的。
2. MVP Profile 不是另一套架构，而是在这些模块上选择最低可用实现。

## 7. 8 个稳定模块

### 7.1 Asset Layer

**Responsibility**

Asset Layer 管理所有评测资产，包括：

- tasks；
- prompts；
- skills；
- rubrics；
- evaluation presets；
- validation rules；
- workspace templates；
- examples。

它负责让评测输入成为可引用、可版本化、可快照的对象。

**MVP implementation**

MVP 可以使用本地文件作为资产来源：

- YAML / JSON 定义 tasks 和 configurations；
- Markdown 保存 task description 和 rubric；
- 本地目录保存 skill；
- 简单 schema 校验资产结构；
- run 开始前生成 asset snapshot。

**Future implementations**

未来可以扩展为：

- Git repo backed task library；
- PromptHub integration；
- skill registry；
- shared rubric library；
- asset version comparison；
- import/export；
- team-level task collections。

**关键边界**

Asset Layer 不执行 agent，不评分，不决定胜负。

它只提供稳定、可快照的输入资产。Execution Kernel 和 Evaluation Layer 消费这些资产，但不应该直接修改资产定义。

---

### 7.2 Configuration Layer

**Responsibility**

Configuration Layer 定义结果矩阵的列，也就是：

```text
Configuration = Agent × Skill(optional) × Environment × Params × Repetitions
```

它负责把用户想比较的对象展开为可执行的 run plan。

**MVP implementation**

MVP 可以支持：

- 本地 `eval.yaml` 或等价配置文件；
- `AgentSpec`；
- `SkillSpec` 可选；
- `WorkspaceSpec`；
- repetitions；
- timeout；
- params；
- Python Pydantic schema；
- TypeScript zod schema；
- UI 中展示和编辑基础配置。

**Future implementations**

未来可以支持：

- configuration presets；
- matrix builder；
- parameter sweep；
- agent version registry；
- skill version registry；
- environment profiles；
- configuration diff；
- historical configuration reuse。

**关键边界**

Configuration Layer 负责定义“要跑什么组合”，但不负责“怎么跑”。

它输出 run plan。Execution Kernel 根据 run plan 执行。Evaluation Layer 根据结果评分。Decision Layer 根据评分和 evidence 做比较。

---

### 7.3 Execution Kernel

**Responsibility**

Execution Kernel 是执行层核心，负责：

- 将 `Tasks × Configurations × Repetitions` 展开为执行单元；
- 调用 Agent Adapter；
- 管理并发；
- 管理 timeout；
- 收集 exit status；
- 收集 stdout / stderr；
- 标记 run result 状态；
- 写入初始 artifact。

**MVP implementation**

MVP 可以采用自写 Python 执行层：

- `asyncio` 并发执行；
- subprocess 调用 agent；
- stdin 或文件传参；
- 禁止 shell 字符串插值；
- timeout；
- 每个 execution unit 生成一个 `RunResult`；
- 本地 `.micro-eval/` 保存结果。

**Future implementations**

未来可以扩展为：

- job queue；
- remote worker；
- distributed execution；
- retry policy；
- richer cancellation；
- resource-aware scheduling；
- OpenHands 执行层适配。

**关键边界**

Execution Kernel 不应该理解具体 agent 的内部协议，也不应该理解评分语义。

它只负责可靠执行和收集原始结果。Agent 细节属于 Agent Adapter Layer。评分属于 Evaluation Layer。可复现环境属于 Environment/Reproducibility Layer。

---

### 7.4 Agent Adapter Layer

**Responsibility**

Agent Adapter Layer 把不同 agent 的调用方式统一成稳定 contract。

它负责：

- command；
- input mode；
- output mode；
- timeout；
- environment variables；
- skill mount；
- tool allowlist；
- exit code interpretation；
- result normalization。

**MVP implementation**

MVP 可以只支持本地 CLI agent：

- command 数组；
- stdin input；
- file input；
- stdout output；
- artifact directory output；
- timeout；
- exit code；
- 基础错误分类。

**Future implementations**

未来可以支持：

- Claude Code adapter；
- OpenHands adapter；
- HTTP agent adapter；
- custom SDK adapter；
- containerized agent；
- remote agent；
- multi-step agent protocol；
- richer tool permission model。

**关键边界**

Agent Adapter 只负责“如何调用 agent 并标准化输出”。

它不决定任务是否成功，不直接写决策报告，不绕过 Execution Kernel。所有 adapter 必须遵守统一 invocation contract，这样后续新增 agent 不会破坏 Run / ResultMatrix 模型。

---

### 7.5 Environment/Reproducibility Layer

**Responsibility**

Environment/Reproducibility Layer 负责同起点和可复现性。

它管理：

- workspace；
- git repo；
- commit；
- worktree；
- setup commands；
- resource limits；
- sandbox；
- tool allowlist；
- environment variables；
- context budget；
- snapshot；
- comparability gate。

**MVP implementation**

MVP 可以使用：

- git worktree 隔离；
- blank workspace；
- files workspace；
- setup commands；
- workspace snapshot；
- repo commit 记录；
- run 前检查是否具备可比性信息。

**Future implementations**

未来可以支持：

- Docker sandbox；
- per-task container image；
- CPU / memory / network limits；
- remote runner；
- deterministic dependency cache；
- richer filesystem snapshot；
- cloud workspace；
- reproducibility verification。

**关键边界**

这个模块的输出不是“目录路径”这么简单，而是 `EnvironmentSnapshot`。

没有 snapshot 的结果不能和其他结果严肃比较。Decision Layer 在做对比前必须能检查：两个 result 是否来自可比较的起点。

---

### 7.6 Evaluation Layer

**Responsibility**

Evaluation Layer 负责把 execution output 转换成 score、judgement 和 explanation。

它管理：

- deterministic validation；
- manual scoring；
- rubric；
- score scale；
- pass/fail；
- LLM judge；
- DeepEval metric；
- evaluator identity；
- score evidence；
- evaluation version。

**MVP implementation**

MVP 可以支持：

- 基础 validation；
- 人工评分；
- rubric-based manual score；
- pass/fail；
- comment；
- score 与 artifact/evidence 关联；
- 每个 score 记录 rubric version。

**Future implementations**

未来可以支持：

- DeepEval custom metric；
- GEval；
- LLM-as-judge；
- multi-judge ensemble；
- evaluator calibration；
- automatic code validation；
- task-specific metrics；
- hybrid manual + automated scoring；
- score confidence。

**关键边界**

Evaluation Layer 不执行 agent，不管理 workspace，不决定产品层最终推荐。

它输出标准化 `EvaluationResult`，其中必须包含 score、rubric、evidence reference 和 evaluator 信息。Decision Layer 可以基于它做比较，但不能丢掉证据链。

---

### 7.7 Artifact/Trace Layer

**Responsibility**

Artifact/Trace Layer 负责保存和关联所有证据。

它管理：

- stdout；
- stderr；
- generated files；
- diffs；
- logs；
- execution metadata；
- cost；
- latency；
- trace id；
- Langfuse trace；
- screenshots 或其他 task-specific artifacts；
- artifact index。

**MVP implementation**

MVP 可以使用本地 artifact store：

- `.micro-eval/` 下保存 run JSON；
- 每个 result 保存 stdout / stderr；
- 保存输出文件；
- 保存 diff；
- 保存 execution metadata；
- 给每个 artifact 生成稳定 ID；
- UI 可以从 result 链接到 artifact。

**Future implementations**

未来可以支持：

- Langfuse trace；
- OpenTelemetry；
- cost breakdown；
- timeline view；
- trace replay；
- artifact search；
- external blob storage；
- long-term retention policy；
- richer provenance graph。

**关键边界**

Artifact/Trace Layer 是证据层，不是展示层。

任何 score、report、decision 都应该能引用 artifact 或 trace。没有 evidence reference 的结论不应该成为正式评测结论。

---

### 7.8 Decision Layer

**Responsibility**

Decision Layer 负责把 result matrix 转换为可理解的产品结论。

它管理：

- matrix comparison；
- per-task comparison；
- per-configuration summary；
- repetitions aggregation；
- score breakdown；
- cost / latency comparison；
- win/loss/tie；
- report；
- recommendation；
- decision rationale；
- evidence links。

**MVP implementation**

MVP 可以支持：

- ResultMatrix 展示；
- task × configuration 表格；
- score 展示；
- pass/fail 展示；
- artifact link；
- manual conclusion；
- 简单 report 导出。

**Future implementations**

未来可以支持：

- statistical aggregation；
- confidence interval；
- variance analysis；
- trend comparison；
- cost-quality frontier；
- regression detection；
- multi-run comparison；
- richer decision report；
- recommendation assistant。

**关键边界**

Decision Layer 可以生成结论，但不能制造证据。

它必须引用 Evaluation Layer 的 scores 和 Artifact/Trace Layer 的 evidence。任何“哪个 agent 更好”的结论，都必须能回溯到 task、configuration、run result、artifact 和 scoring rationale。

## 8. Maturity levels 示例

Maturity levels 用来表达：每个模块可以逐步增强，但 contract 不变。

MVP Profile 的职责就是选择每个模块当前采用哪个 level。

### 8.1 Agent Adapter

| Level | 能力 | 说明 |
|---|---|---|
| L0 | Local subprocess | 本地 command 调用，stdin/file 输入，stdout/file 输出 |
| L1 | Declared I/O contract | 明确 input_mode、output_mode、timeout、exit status、artifact path |
| L2 | Named adapters | 为不同 agent 类型提供 adapter，例如 Claude Code、OpenHands、HTTP agent |
| L3 | Managed/remote adapters | 支持远程 agent、container agent、权限模型、复杂协议 |

MVP 建议选择：L0 或 L1。

关键要求：即使 MVP 只支持本地 subprocess，也必须通过 Agent Adapter contract 调用，不能在 Execution Kernel 里硬编码某个 agent 的特殊行为。

---

### 8.2 Workspace

| Level | 能力 | 说明 |
|---|---|---|
| L0 | Temporary/blank workspace | 每次 run 创建临时空目录或简单文件目录 |
| L1 | Git worktree snapshot | 基于 repo commit 创建 worktree，记录 commit、setup commands、workspace metadata |
| L2 | Docker sandbox | 使用 container image、资源限制、隔离网络和 filesystem |
| L3 | Reproducible remote runner | 支持远程可复现 runner、缓存、资源声明和环境验证 |

MVP 建议选择：L1。

关键要求：MVP 可以不做 Docker，但不能不记录 workspace 起点。没有 workspace snapshot，结果矩阵就不可信。

---

### 8.3 Evaluation

| Level | 能力 | 说明 |
|---|---|---|
| L0 | Manual pass/fail | 人工判断通过/失败，附 comment |
| L1 | Deterministic validation | 使用脚本、命令、文件检查或规则进行基础验证 |
| L2 | Rubric scoring | 基于 rubric 做结构化评分，支持多维度分数 |
| L3 | LLM/DeepEval judge | 接入 DeepEval、GEval、LLM-as-judge、多评委或自动评分组合 |

MVP 建议选择：L0 + 部分 L1，必要时支持 L2 的数据结构但不强制复杂 UI。

关键要求：即使是人工评分，也必须记录 rubric、score、comment 和 evidence reference。

---

### 8.4 Statistics

| Level | 能力 | 说明 |
|---|---|---|
| L0 | Raw results | 展示每个 task/configuration/repetition 的原始结果 |
| L1 | Basic aggregation | 计算平均分、成功率、成本、耗时 |
| L2 | Variance/confidence | 展示方差、置信区间、异常值、重复实验稳定性 |
| L3 | Longitudinal analysis | 跨 run 趋势、回归检测、版本质量变化 |

MVP 建议选择：L0，若 repetitions 已经存在，可以支持少量 L1。

关键要求：不要为了 MVP 简化而删除 repetitions 维度。即使 UI 暂时不做复杂统计，数据模型也要保留 repetition identity。

---

### 8.5 Trace

| Level | 能力 | 说明 |
|---|---|---|
| L0 | stdout/stderr | 保存基础进程输出 |
| L1 | Local artifact index | 保存 files、diff、metadata、cost/latency，并建立 artifact id |
| L2 | Langfuse trace | 接入 Langfuse，记录 trace、span、cost、latency |
| L3 | Full observability graph | 支持跨系统 trace、replay、搜索、长期存储和告警 |

MVP 建议选择：L1。

关键要求：MVP 可以不接 Langfuse，但必须有本地 artifact/trace contract。否则后续无法把本地证据迁移到外部观测系统。

---

### 8.6 Decision Report

| Level | 能力 | 说明 |
|---|---|---|
| L0 | Matrix view | 展示 task × configuration 的结果矩阵 |
| L1 | Evidence-linked summary | 生成包含结论、分数、证据链接的简报 |
| L2 | Comparative analysis | 支持 cost-quality tradeoff、稳定性、失败模式、敏感性分析 |
| L3 | Decision workflow | 支持跨 run 决策记录、批准、历史追踪和团队协作 |

MVP 建议选择：L0 + 部分 L1。

关键要求：报告不是单独写一段主观结论，而是要绑定 ResultMatrix、scores 和 evidence links。

## 9. 核心原则

### 9.1 MVP 是 Profile，不是 fork

MVP 不应该重新定义一套自己的架构。

MVP 是在 Unicorn Design 的模块化架构上，为每个模块选择最低可用 maturity level。

这意味着：

- 模块名称不变；
- 核心数据模型不变；
- 跨模块 contract 不变；
- 可复现性和证据链原则不变；
- 只是在实现能力上选择低等级版本。

### 9.2 MVP 可以低配实现，但不能绕过模块 contract

MVP 可以：

- 用本地文件代替资产库；
- 用 subprocess 代替复杂 agent runtime；
- 用 git worktree 代替 Docker；
- 用人工评分代替 LLM judge；
- 用本地 JSON 代替数据库；
- 用本地 artifact 代替 Langfuse；
- 用矩阵表格代替高级统计报告。

MVP 不可以：

- 跳过 Agent Adapter，直接在 run 逻辑里硬编码 agent；
- 跳过 Workspace Snapshot，直接在当前目录运行后比较结果；
- 跳过 Artifact/Trace，只保存最终分数；
- 跳过 rubric 和 evidence，只保存主观结论；
- 跳过 ResultMatrix，直接生成不可追溯的报告；
- 把 MVP 数据结构设计成无法升级到完整模型的临时结构。

### 9.3 长期不变量优先于短期 UI 便利

UI 可以先简单，但底层 identity 和 evidence chain 不能随意简化。

例如：

- `task_id` 必须稳定；
- `configuration_id` 必须稳定；
- `run_id` 必须稳定；
- `result_id` 必须能定位到 task/configuration/repetition；
- `artifact_id` 必须能被 score 和 report 引用；
- `snapshot_id` 必须能说明可比性。

这些不是后期高级功能，而是系统可信度的基础。

### 9.4 实现可以替换，contract 不应频繁替换

MVP 的实现可以被替换：

- local files 可以换成 asset registry；
- subprocess 可以换成 OpenHands；
- git worktree 可以加 Docker；
- manual scoring 可以加 DeepEval；
- local artifact 可以加 Langfuse；
- simple matrix 可以加统计报告。

但这些替换应该发生在模块内部，而不是推翻整个数据流。

## 10. 需要补强的完整设计点

重构 Unicorn Design 时，建议重点补强以下五类内容。

### 10.1 Module ownership

每个模块都需要明确 ownership。

这里的 ownership 不是指团队成员归属，而是指架构责任归属：

- 哪个模块拥有哪类对象；
- 哪个模块可以创建对象；
- 哪个模块可以修改对象；
- 哪个模块只能读取对象；
- 对象的生命周期由谁管理；
- 错误由哪个模块负责分类和上报。

例如：

- Asset Layer owns `Task`, `Rubric`, `SkillSpec` definitions；
- Configuration Layer owns `Configuration` and matrix expansion；
- Execution Kernel owns `Run` orchestration state；
- Environment Layer owns `EnvironmentSnapshot`；
- Evaluation Layer owns `EvaluationResult`；
- Artifact/Trace Layer owns `Artifact` and `TraceRef`；
- Decision Layer owns `DecisionReport`。

没有 ownership，模块边界会在实现中快速混乱。

### 10.2 Cross-module contracts

模块之间必须有明确 contract，而不是“读同一个 JSON”。

需要定义：

- 输入对象；
- 输出对象；
- 必填字段；
- 可选字段；
- 错误结构；
- version；
- ID 引用关系；
- artifact 引用方式；
- score 引用方式；
- snapshot 引用方式。

关键 contract 示例：

- `AssetSnapshot`；
- `RunPlan`；
- `AgentInvocation`；
- `EnvironmentSnapshot`；
- `ExecutionResult`；
- `ArtifactRef`；
- `EvaluationResult`；
- `ResultMatrix`；
- `DecisionReport`。

MVP 可以只实现 contract 的最小字段，但字段语义必须和长期设计一致。

### 10.3 Stable IDs

micro-eval 的可追溯性依赖稳定 ID。

建议完整设计明确以下 ID：

| ID | 作用 |
|---|---|
| `task_id` | 标识一个评测任务 |
| `task_version` | 标识任务内容版本 |
| `rubric_id` | 标识评分标准 |
| `rubric_version` | 标识评分标准版本 |
| `agent_id` | 标识被评测 agent |
| `skill_id` | 标识 skill |
| `skill_version` | 标识 skill 版本 |
| `configuration_id` | 标识一个配置列 |
| `environment_snapshot_id` | 标识执行起点 |
| `run_id` | 标识一次 run |
| `result_id` | 标识一个 task/configuration/repetition 结果 |
| `artifact_id` | 标识一个证据对象 |
| `evaluation_id` | 标识一次评分 |
| `decision_report_id` | 标识一个决策报告 |

Stable IDs 的目的不是形式主义，而是让结论可追溯、可比较、可复现。

### 10.4 Evidence as shared currency

micro-eval 里所有重要结论都应该以 evidence 为共同货币。

Evidence 可以是：

- stdout；
- stderr；
- generated file；
- diff；
- log；
- trace span；
- cost record；
- latency record；
- validation output；
- screenshot；
- manual comment；
- judge explanation。

Evaluation Layer 不应该只输出分数，而应该输出：

- score；
- explanation；
- evidence refs；
- rubric refs；
- evaluator refs。

Decision Layer 不应该只输出“Agent A 更好”，而应该输出：

- 哪些 task 上更好；
- 分数差异是什么；
- 成本和耗时如何；
- 失败模式是什么；
- 证据链接是什么；
- 这个结论依赖哪些 evaluation result。

这样才能把“我觉得这个 agent 更强”变成“基于这些 task、这些配置、这些证据和这些评分标准，Agent A 在这个范围内更强”。

### 10.5 Snapshot as comparability gate

Snapshot 是可比性的门槛。

一个 result 能否进入同一个 ResultMatrix，不只取决于它是否跑完，还取决于它是否来自可比较的起点。

完整设计需要明确：

- task snapshot；
- rubric snapshot；
- agent snapshot；
- skill snapshot；
- workspace snapshot；
- environment snapshot；
- configuration snapshot；
- tool allowlist snapshot；
- context budget snapshot；
- dependency/setup snapshot。

如果两个结果的关键 snapshot 不一致，Decision Layer 必须能提示：

- 这些结果不可直接比较；
- 或者只能作为弱比较；
- 或者需要用户确认差异可接受。

MVP 可以先做简单 snapshot，但不能完全没有 snapshot。

## 11. 推荐下一步

### 11.1 先重构 `2026-06-01-unicorn-design-v1.md` 为 Modular Architecture

建议先把现有 Unicorn Design 重构为模块化完整架构文档。

重构目标：

- 保留完整设计的产品判断和长期不变量；
- 把内容按 8 个稳定模块组织；
- 每个模块写清 responsibility、data owned、inputs、outputs、contracts、maturity levels；
- 把未来实现放到对应模块下，而不是散落成路线图愿望；
- 明确哪些原则是 MVP 也必须遵守的硬约束。

建议结构：

```text
1. Product intent and invariants
2. Core domain model
3. Modular architecture overview
4. Stable modules
   4.1 Asset Layer
   4.2 Configuration Layer
   4.3 Execution Kernel
   4.4 Agent Adapter Layer
   4.5 Environment/Reproducibility Layer
   4.6 Evaluation Layer
   4.7 Artifact/Trace Layer
   4.8 Decision Layer
5. Cross-module contracts
6. Stable IDs and snapshots
7. Evidence model
8. Maturity levels
9. Non-goals and boundaries
```

### 11.2 再新建 `2026-06-02-mvp-profile.md`

在 Modular Unicorn Design 稳定后，再新建 MVP Profile。

MVP Profile 不重新解释完整系统，只声明当前 MVP 选择。

建议结构：

```text
1. MVP goal
2. MVP user journey
3. Selected maturity levels
4. MVP module-by-module implementation
5. Required contracts even in MVP
6. Explicit non-goals
7. Data persistence shape
8. UI scope
9. Test strategy
10. Upgrade path
```

MVP Profile 中可以明确类似选择：

| Module | MVP level | MVP choice |
|---|---:|---|
| Asset Layer | L0/L1 | local YAML/Markdown assets with snapshot |
| Configuration Layer | L1 | explicit Configuration model and matrix expansion |
| Execution Kernel | L1 | Python asyncio subprocess runner |
| Agent Adapter Layer | L0/L1 | local CLI adapter with stdin/file I/O |
| Environment/Reproducibility Layer | L1 | git worktree and workspace snapshot |
| Evaluation Layer | L0/L1 | manual score plus basic validation |
| Artifact/Trace Layer | L1 | local artifact index under `.micro-eval/` |
| Decision Layer | L0/L1 | matrix view plus evidence-linked summary |

### 11.3 建立文档防漂移规则

后续任何新增能力，都应该落到以下两种修改之一：

1. 更新 Unicorn Design 的模块 contract 或 maturity level；
2. 更新 MVP Profile 选择的 level 或实现范围。

不应该新增一个和现有模块体系无关的临时设计。

判断标准很简单：

- 如果是长期结构变化，改 Unicorn Design；
- 如果是当前阶段选择变化，改 MVP Profile；
- 如果是取舍依据变化，改 Research Doc；
- 如果是用户和业务目标变化，改 BRD。

### 11.4 最终目标

最终文档体系应该让任何实现者都能清楚知道：

- micro-eval 长期架构是什么；
- MVP 为什么只做这些；
- MVP 哪些地方可以简化；
- MVP 哪些 contract 不能破坏；
- 后续增强应该接在哪个模块；
- 一个评测结论如何从 BRD 目标一路追溯到 task、configuration、run result、artifact、score 和 report。

这套策略的核心不是“多写文档”，而是避免两种失败：

- 完整设计过重，导致 MVP 无法落地；
- MVP 过轻，导致完整设计无法复用。

正确做法是：

> 让 Unicorn Design 稳定模块和长期不变量，  
> 让 MVP Profile 选择最低可用实现，  
> 让 Research Doc 记录取舍依据，  
> 让 BRD 持续约束用户价值。
