---
status: partially-completed
---

# 用户文档设计体系重组计划

> **状态注记（2026-07-02）：** 核实结论——Task 0–7 均有对应的 `site/` git 提交（`git log --oneline -- site/` 可见 `43b8815` 术语清理 → `1a05a63`/`d655e1f` Design System 页 → `a75d56f` sidebar 重构 → `a6124ea` core-concepts 拆分 → `3ae49ab` 锚定 → `67baf66` 实现细节清理 → `e3a0b07` 入口页链接），已完成。但 **Task 8（最终验证）未完成**：git log 中无 "final verification"/"final commit" 记录；实测发现 Task 8 Step 4（术语一致性检查）本应统一 "RunCell" → "Cell"，但 `site/guide/execution.md` 与 `site/zh/guide/execution.md` 第 26 行仍残留 `RunCells = Tasks × Configurations × range(repetitions)`。剩余项：
> 1. `site/guide/execution.md:26` 与 `site/zh/guide/execution.md:26` 的 "RunCells" 需改为 "Cells"。
> 2. Task 8 Step 5（Final commit）未执行——需在完成上述清理后补一次最终验证与 commit。
> 其余 Step 4 检查项（Evidence/Evidence Chain 用词、DecisionStatus 6 值一致性、Run/ResultMatrix 定义一致性）经抽查未见问题。

> **v3:** 根据 Codex re-review（2 轮）修补残余缺口：Task 0 文件列表补入 tasks.md；全文 "六个核心对象" 统一为含 Run 的 7 对象表述；anchor `#six-core-objects` → `#core-objects`；core-concepts.md 处理方式统一为"改写为跳转页"（不删除）；RunCell 术语在用户文档中统一为 Cell。
>
> **v2:** 根据 Codex review 修订。回应 8 条审查意见（3 high, 4 medium, 1 low）：
> - High #1: 修正 "Same-start" 为 per-task-across-configs 精度，而非 whole-run 级别
> - High #2: 新增 Task 0（术语/字段名一致性前置清理），防止旧冲突固化到新结构
> - High #3: Task 8 验证范围从 grep core-concepts 扩展为全站 link+anchor 扫描
> - Medium #4: 核心对象补入 Run 和 ResultMatrix，拆分表增加去向
> - Medium #5: security.md 纳入 Task 0 轻量清理范围
> - Medium #6: core-concepts 跳转页保留旧 heading anchor stub
> - Medium #7: Task 8 增加中英文对称性检查
> - Low #8: Task 5 实现细节清理范围扩展到所有 guide 页

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重组 micro-eval 的用户文档站点（`site/`），从当前按内部模块平铺的结构，改为以设计体系为骨架、按用户旅程组织的结构。使用户能快速建立正确的心智模型，并在未来添加新功能时有清晰的文档落点。

**Scope:** 仅涉及 `site/` 目录下的用户/贡献者文档和 VitePress 配置。**不涉及**内部开发文档（Unicorn spec、engineering guidelines、CLAUDE.md 等）——它们服务于不同受众，是独立的关注点。

---

## Part 0: 发现与决策推理

### 0.1 当前用户文档的问题

micro-eval 的文档站点（VitePress，中英双语，44 页）内容质量不错——每一页单独看都写得清楚。但整体信息架构存在三个结构性问题：

**问题一：按内部模块平铺，而非按用户旅程组织**

当前 sidebar 的"核心指南"部分：

```
核心概念 → 配置详解 → 任务与验证 → 执行层 → 评分系统 → 决策与 Caveat
→ Workspace 隔离 → 趋势分析 → 安全模型
```

这 9 页对应的是系统内部的 8 个模块（合并了若干），而不是用户的操作流程。用户想知道的是"我怎么比较两个 agent"，但必须按模块顺序读 9 页才能拼出完整图景。

对比用户的实际旅程：

```
我要比什么？→ 怎么描述"正确"？→ 跑起来 → 看结果 → 做判断
```

当前结构缺少这条主线。

**问题二：概念、配置参考和实现细节混杂在同一页**

以几页为例：

| 页面 | 混杂情况 |
|------|---------|
| `core-concepts.md` | 列出 13 个领域对象（Configuration, AgentSpec, Task, WorkspaceSpec, Run, RunPlan, RunCell, Expectation, EvaluationResult, Evidence Chain, Decision, DecisionStatus, Caveat），像一个术语表而不是心智模型引导 |
| `execution.md` | 同时讲"矩阵展开是什么"（概念）和"asyncio semaphore 如何控制并发"（实现细节） |
| `workspace-isolation.md` | 同时讲"为什么起点一致很重要"（设计原则）和"Seatbelt/Bubblewrap 策略如何配置"（高级用法） |
| `trend-analysis.md` | 同时讲"跨 run 趋势比较"（功能）和"SQLite index 内部结构"（实现细节） |

结果是：初次使用者被实现细节淹没，高级用户找不到需要的配置参考。

**问题三：设计体系未被显式表达**

micro-eval 有一套非常清晰的设计体系（决策闭环、三个设计张力、核心领域对象、诚实边界原则），但它从未作为一个独立的、面向用户的概念被呈现。这套体系散落在各页的零碎段落里：

- 决策闭环在 `index.md` 的 mermaid 图里提过一次
- "Evidence-first" 在 `decision.md` 的 Philosophy 段提过
- "Same-start" 在 `workspace-isolation.md` 的 Why This Matters 段提过
- "Honest boundaries" 在 `decision.md` 的 Conservative Defaults tip 里提过
- 核心对象在 `core-concepts.md` 里平铺列出 13 个（含 7 个二级对象），没有区分主次

用户从来没有机会在一个地方看到"这个工具的核心设计思想是什么"。

### 0.2 从代码和内部设计文档中提炼出的设计体系

通过阅读 Unicorn Design、strategy doc 和实际代码，micro-eval 的设计体系可以清晰地表述为：

**核心公式：**
```
Run = Tasks × Configurations × Repetitions → ResultMatrix → Decision
```

**决策闭环（系统的脊柱）：**
```
定义任务 → 配置对比组 → 确保同起点 → 并行执行 → 收集证据 → 诚实统计 → 出结论
                                                                          ↓
                                                    promote / rollback / rerun
```

**三个设计张力（解释所有"为什么这样设计"）：**

| 张力 | 面向用户的含义 | 你在产品中看到的体现 |
|------|--------------|-------------------|
| 证据优先 | 每个结论都能点进去看到原始产物 | Evidence Chain、结果页上的 artifact 链接、Decision 必须引用 Evaluation |
| 同起点 | 同一个 Task 跨不同 Configuration/Repetition 执行时，必须从等价的 workspace snapshot 开始；不同 Task 行可以有不同 workspace | SameStartSnapshot、workspace 隔离、`not_comparable` 状态 |
| 诚实边界 | "样本不足无法判断"是正确答案 | 6 种 DecisionStatus（含 `inconclusive`）、Caveat 机制、confidence 分级 |

**核心领域对象（用户需要理解的）：**

```
Task ──┐
       ├── Run ── Cell ── Evidence ── Evaluation ── Decision
Config ─┘
```

| 对象 | 矩阵角色 | 一句话 |
|------|---------|--------|
| **Task** | 行 | 要测什么（prompt + workspace + 验收标准） |
| **Configuration** | 列 | 拿什么测（agent + 参数 + 环境） |
| **Run** | 矩阵本身 | 一次完整的 Tasks × Configs × Reps 执行，产出 ResultMatrix |
| **Cell** | 格 | 一次原子执行 (task × config × rep) |
| **Evidence** | — | 执行产出的事实（stdout、diff、cost），不可变、已脱敏 |
| **Evaluation** | — | 对证据的打分（验证器 → LLM judge → 人工标注） |
| **Decision** | — | 矩阵级别的结论（improved / regressed / inconclusive + caveats） |

当前 `core-concepts.md` 列出了 13 个对象但没有区分主次。实际上用户只需先理解上面这些核心对象，其余（AgentSpec、WorkspaceSpec、RunPlan、RunCell、Expectation、DecisionStatus、Caveat、ArtifactRef）是二级概念，在具体操作时按需学习即可。

### 0.3 目标信息架构

将当前"9 页模块平铺"改为四段式用户旅程：

```
┌─ 认识 ──────────────────────────────────────────────────────┐
│  What is micro-eval?    — 已有，基本不动                      │
│  Getting Started        — 已有，基本不动                      │
│  Design System (NEW)    — 决策闭环 + 3 张力 + 核心对象        │
├─ 使用 ──────────────────────────────────────────────────────┤
│  Defining Tasks         — 从 tasks.md 重构                   │
│  Configuring Comparisons — 从 configuration.md 重构           │
│  Running & Results      — 合并 execution.md 的用户可见部分     │
│  Evaluation & Scoring   — 已有，小幅调整                      │
│  Making Decisions       — 从 decision.md 重构                 │
├─ 进阶 ──────────────────────────────────────────────────────┤
│  Workspace & Sandboxing — 从 workspace-isolation.md 重构      │
│  Trend Analysis         — 已有，去掉实现细节                   │
│  Security Model         — 已有，基本不动                      │
├─ 参考 ──────────────────────────────────────────────────────┤
│  CLI / eval.yaml / task.yaml / Data Model / API / Web UI     │
│  （已有，不动）                                               │
└──────────────────────────────────────────────────────────────┘
```

**与当前结构的关键差异：**

| 变化 | 原因 |
|------|------|
| 新增 "Design System" 页 | 让用户在操作之前就建立正确的心智模型 |
| "Core Concepts" 页改写为跳转页 | 核心对象（Task、Configuration、Run、Cell、Evidence、Evaluation、Decision）进 Design System，二级概念分散到各使用页；旧页保留 heading anchor stub 防止外部深链 404 |
| "Execution" 页重命名为 "Running & Results" | 用户不关心"执行层"，关心"怎么跑、结果在哪" |
| Sidebar 从"核心指南"一个大组改为"认识/使用/进阶"三组 | 让不同阶段的用户快速找到对应内容 |
| 各页去掉实现细节 | asyncio/semaphore/SQLite 等属于贡献者关心的内容，不属于用户指南 |

### 0.4 持久性验证：未来功能如何在这个架构中落地

| 未来功能 | "认识"层影响 | "使用"层影响 | "进阶"层影响 | "参考"层影响 |
|---------|-------------|-------------|-------------|-------------|
| Global Registry (v0.3.5) | 无 | "Running & Results" 加一段多项目说明 | 可选：加"Multi-Project"进阶页 | 更新 CLI reference |
| 新 Evaluation 方法（如 GEval） | 无 | "Evaluation & Scoring" 加一段 | 无 | 更新 eval.yaml Schema |
| 新隔离级别（如 Docker） | 无 | 无 | "Workspace & Sandboxing" 加一段 | 更新 eval.yaml Schema |
| 新 Expectation 类型 | 无 | "Defining Tasks" 加一段 | 无 | 更新 task.yaml Schema |
| 新 CLI 子命令 | 无 | 视情况 | 无 | 更新 CLI reference |

**模式：** Design System 页几乎不需要改（除非产品的根本模型变了）。日常功能增长落在"使用/进阶"页和"参考"页。这正是我们要的持久性。

### 0.5 预期效果

**对初次用户：**
- 读完 "What is micro-eval?" + "Design System" 就能理解产品的核心思想，不需要读完全部 9 页
- Sidebar 的"使用"组直接对应"我要做什么"的顺序，不再需要猜"执行层"在讲什么

**对日常使用者：**
- 每个"使用"页独立完整，想查"怎么配置 LLM judge"直接去 "Evaluation & Scoring"
- 实现细节不再干扰操作指引

**对贡献者：**
- Design System 页提供完整的概念框架，新贡献者不需要读 Unicorn 就能理解用户侧的概念体系
- 内部开发文档（Unicorn 等）继续服务深度工程决策，两套文档各司其职

**对文档维护者：**
- 添加新功能时，有明确的落点："这是使用页的内容还是进阶页的内容？"
- Design System 页是稳定的，不需要随每个版本更新

---

## Part 1: 文件变更清单

### 新建文件

| 文件 | 内容 | 长度估计 |
|------|------|---------|
| `site/guide/design-system.md` | 决策闭环 + 3 张力 + 核心对象 + 设计原则 | ~150 行 |
| `site/zh/guide/design-system.md` | 上述的中文版 | ~120 行 |

### 重写文件（结构性改变）

| 文件 | 变更描述 |
|------|---------|
| `site/.vitepress/config.ts` | Sidebar 从 "Introduction + Core Guide" 两组改为 "Get Started + Using micro-eval + Advanced + Reference" 四组；中英文同步 |
| `site/guide/core-concepts.md` | **改写为跳转页（保留旧 anchor stub）**：核心对象→ design-system.md；二级概念→各使用页 |
| `site/zh/guide/core-concepts.md` | 同上中文版 |
| `site/guide/execution.md` | 重命名为概念，去掉 asyncio/semaphore 实现细节，聚焦"跑一次 run 会发生什么、结果在哪" |
| `site/zh/guide/execution.md` | 同上中文版 |

### 修改文件（内容调整，结构不变）

| 文件 | 变更描述 |
|------|---------|
| `site/guide/configuration.md` | 开头加一段"在 Design System 中，Configuration 是矩阵的列"的上下文锚定 |
| `site/guide/tasks.md` | 开头加上下文锚定；把 WorkspaceSpec、Expectation 等二级概念的定义从 core-concepts 迁移到这里（就地解释，不再让用户跳页） |
| `site/guide/evaluation.md` | 小幅调整：开头加上下文锚定 |
| `site/guide/decision.md` | 小幅调整：开头加上下文锚定；确认 DecisionStatus 6 值与 design-system 一致 |
| `site/guide/workspace-isolation.md` | 去掉 Provider 内部实现细节（Seatbelt/Bubblewrap 代码路径等），保留用户可配置的内容 |
| `site/guide/trend-analysis.md` | 去掉 SQLite index 内部结构段，保留用户可见的功能和配置 |
| `site/guide/index.md` | 更新 "Next Steps" 链接，指向新的 design-system 页 |
| `site/guide/getting-started.md` | 末尾"Next Steps"更新为指向 design-system |
| `site/zh/guide/*.md` | 以上所有改动的中文镜像 |

### 不动的文件

| 文件 | 理由 |
|------|------|
| `site/reference/*.md` （全部 6 页） | 参考手册是查找型文档，结构合理不动（但 Task 8 会检查 reference→guide 的 anchor 链接是否仍有效） |
| `site/examples/*.md` （全部） | Examples 已按场景组织，不需要改 |
| `site/index.md` | 首页 landing，不动 |
| 内部文档全部 | 不在本计划范围内 |

> **注意：** `site/guide/security.md` 原计划标记为"不动"，但 Codex review 发现其中包含 `asyncio.create_subprocess_exec` 代码片段和实现细节，与"guide 页去掉实现细节"的原则不一致。已将其纳入 Task 0 的轻量清理范围。

---

## Part 2: 任务分解

### Task 0: 术语/字段名一致性前置清理

**Files:**
- Modify: `site/guide/configuration.md`
- Modify: `site/guide/tasks.md`
- Modify: `site/guide/execution.md`
- Modify: `site/guide/workspace-isolation.md`
- Modify: `site/guide/evaluation.md`
- Modify: `site/guide/decision.md`
- Modify: `site/guide/security.md`
- 以及对应中文版

> **Codex review 发现：** 当前 guide 页和 reference 页之间已有多处字段名/术语不一致（包括 tasks.md 中的 Expectation type 名 `run` vs reference 中的 `command`）。如果不先清理，后续的内容搬迁会把旧冲突固化到新结构里。

- [ ] **Step 1: 建立术语对照表**

以 `site/reference/eval-yaml.md` 和 `site/reference/task-yaml.md` 中的 schema 字段名为 ground truth，扫描所有 guide 页找到以下类型的不一致：
- 字段名差异（如 guide 中的 `max_output_bytes` vs reference 中的 `output_cap_bytes`）
- 配置路径差异（如 guide 中的 `sandbox.level` vs reference 中的 `isolation_level`）
- Expectation type 名差异（如 guide 中的 `run` vs reference 中的 `command`）

产出一个 checklist，每条标注：guide 中的错误用法 → reference 中的正确用法 → 涉及的文件和行。

- [ ] **Step 2: 统一字段名**

按 checklist 逐条修复 guide 页中的字段名，使其与 reference schema 一致。

- [ ] **Step 3: security.md 轻量清理**

> **Codex review 发现：** security.md 虽然是用户视角，但包含 `asyncio.create_subprocess_exec` 代码片段和 Jinja2/Next.js 实现细节。

去掉 security.md 中的代码实现细节（Python/TS 代码片段），保留用户可理解的安全模型描述。

- [ ] **Step 4: 中文版同步**

- [ ] **Step 5: Commit**

```bash
git add site/guide/ site/zh/guide/
git commit -m "docs(site): normalize field names and terminology against reference schema"
```

---

### Task 1: 创建 Design System 页（英文）

**Files:**
- Create: `site/guide/design-system.md`

这是整个重组的基石页面。它把散落在各处的设计思想集中呈现给用户。

- [ ] **Step 1: 编写 design-system.md**

结构：

```markdown
# Design System

micro-eval 的所有功能服务于一条决策闭环。理解这条闭环和它背后的
设计原则，比记住每个配置字段更重要。

## The Decision Loop

[核心公式 + 闭环管道图]
[强调：闭环断了，产品就退回"展示结果让用户猜"]

## Three Design Tensions

[表格：张力名 / 面向用户的含义 / 在产品中的体现]
- Evidence-first
- Same-start
- Honest boundaries

## Core Objects

[数据流图：Task + Config → Run → Cell → Evidence → Evaluation → Decision]
[核心对象表：Task、Configuration、Run、Cell、Evidence、Evaluation、Decision]
[Run 是承载一次矩阵执行的容器；ResultMatrix 是 Run 产出的用户可见产物]
[明确说明：这些是核心，其余（AgentSpec、WorkspaceSpec 等）是操作时按需了解的细节]

## What These Principles Mean for You

[3-4 条实操暗示，比如：]
- 如果你的 run 报告 `inconclusive`，这不是 bug，而是在告诉你样本不够
- 如果两个 config 的 workspace 不同，结果会被标记为 `not_comparable`
- 每个分数都有证据链接——你永远可以点进去看原始产物
```

- [ ] **Step 2: 验证自包含性**

读一遍，确认：一个从未见过 micro-eval 的用户读完此页后，能回答"这个工具的核心思想是什么"和"结果页上那些状态是什么意思"。如果不能，补齐缺口。

- [ ] **Step 3: Commit**

```bash
git add site/guide/design-system.md
git commit -m "docs(site): add Design System page for user-facing concept framework"
```

---

### Task 2: 创建 Design System 页（中文）

**Files:**
- Create: `site/zh/guide/design-system.md`

- [ ] **Step 1: 翻译 design-system.md 为中文**

不是机械翻译，而是中文用户习惯的表述。术语保留英文原文（如 Configuration、Decision、Caveat）并加中文注释。

- [ ] **Step 2: Commit**

```bash
git add site/zh/guide/design-system.md
git commit -m "docs(site): add Chinese Design System page"
```

---

### Task 3: 重构 Sidebar（config.ts）

**Files:**
- Modify: `site/.vitepress/config.ts`

- [ ] **Step 1: 修改英文 sidebar**

从：
```
Introduction: What is micro-eval? / Getting Started
Core Guide: Core Concepts / Configuration / Tasks / Execution / Evaluation / Decision / Workspace / Trend / Security
```

改为：
```
Get Started:
  What is micro-eval?
  Getting Started
  Design System            ← NEW

Using micro-eval:
  Defining Tasks           ← was "Tasks & Expectations"
  Configuring Comparisons  ← was "Configuration"
  Running & Results        ← was "Execution"
  Evaluation & Scoring     ← unchanged
  Making Decisions         ← was "Decision & Caveats"

Advanced:
  Workspace & Sandboxing   ← was "Workspace Isolation"
  Trend Analysis           ← unchanged
  Security Model           ← unchanged
```

- [ ] **Step 2: 修改中文 sidebar**

对应中文翻译：

```
入门:
  micro-eval 是什么？
  快速开始
  设计体系                 ← NEW

使用指南:
  定义任务
  配置对比组
  运行与结果
  评分系统
  做出决策

进阶:
  Workspace 与沙箱
  趋势分析
  安全模型
```

- [ ] **Step 3: 验证所有链接路径正确**

注意：页面文件名不一定需要改（VitePress sidebar 的 `text` 和 `link` 是独立的）。只在 sidebar 显示文本变化的情况下，确认 link 仍指向正确的 .md 文件。

- [ ] **Step 4: Commit**

```bash
git add site/.vitepress/config.ts
git commit -m "docs(site): restructure sidebar into Get Started / Using / Advanced / Reference"
```

---

### Task 4: 拆分 core-concepts.md

**Files:**
- Modify: `site/guide/core-concepts.md` → 改写为跳转页（保留旧 heading anchor stub）
- Modify: `site/guide/tasks.md` — 接收 WorkspaceSpec、Expectation 定义
- Modify: `site/guide/configuration.md` — 接收 AgentSpec 定义
- Modify: `site/guide/decision.md` — 确认 DecisionStatus、Caveat 定义完整

当前 core-concepts.md 定义了 13 个对象。拆分规则：

| 对象 | 去向 |
|------|------|
| Configuration, Task, Run, Cell, Evidence Chain, Evaluation, Decision | `design-system.md`（已在 Task 1 中创建） |
| ResultMatrix | `design-system.md`（Run 的产出物，用户在 UI 和报告中直接看到） |
| AgentSpec | `configuration.md`（就地解释，不再跳页） |
| WorkspaceSpec | `tasks.md`（workspace 是 task 的一部分） |
| RunPlan, RunCell | `execution.md`（执行时才需要知道；用户文档正文统一用 "Cell"，RunCell 仅作为 anchor stub 或代码名称说明出现） |
| Expectation | `tasks.md`（验收标准是 task 的一部分） |
| DecisionStatus, Caveat | `decision.md`（已有完整定义，确认即可） |
| EvaluationResult | `evaluation.md`（已有完整定义，确认即可） |

- [ ] **Step 1: 将 AgentSpec 定义段移入 configuration.md**

在 configuration.md 的 "agent:" 配置块之前，加入 AgentSpec 的概念说明（从 core-concepts 迁移，重写为使用上下文）。

- [ ] **Step 2: 将 WorkspaceSpec 和 Expectation 定义段移入 tasks.md**

tasks.md 已经有 workspace 和 expectations 的内容，但没有概念定义。从 core-concepts 迁移定义，融合到现有内容中。

- [ ] **Step 3: 将 RunPlan 定义融入 execution.md，统一 Cell 术语**

execution.md 已经讲了这些概念，但没有用 core-concepts 中的正式定义。对齐术语：用户文档正文统一使用 "Cell"（不用 "RunCell"——那是代码层名称）。RunPlan 可以在执行上下文中首次提及时简单定义。

- [ ] **Step 4: 将 core-concepts.md 改写为跳转页**

```markdown
# Core Concepts

This page has been reorganized into focused guides.

- **[Design System](./design-system)** — the core objects and design principles
- **[Defining Tasks](./tasks)** — WorkspaceSpec, Expectations
- **[Configuring Comparisons](./configuration)** — AgentSpec, parameters
- **[Running & Results](./execution)** — Run, RunPlan, Cell
- **[Making Decisions](./decision)** — DecisionStatus, Caveats

## Configuration {#configuration}

→ Moved to [Design System](./design-system#core-objects) and [Configuring Comparisons](./configuration)

## AgentSpec {#agentspec}

→ Moved to [Configuring Comparisons](./configuration#agentspec)

## Task {#task}

→ Moved to [Design System](./design-system#core-objects) and [Defining Tasks](./tasks)

## WorkspaceSpec {#workspace-spec}

→ Moved to [Defining Tasks](./tasks#workspace)

[... repeat for all former headings ...]
```

保留此页（而非删除）以避免外部链接 404。**保留所有旧 heading 作为 anchor stub**，每个 stub 含一行重定向链接，保护外部深链和搜索引擎索引。

- [ ] **Step 5: 对中文版做同样的拆分**

`site/zh/guide/core-concepts.md` 以及对应的 tasks/configuration/execution/decision 中文版。

- [ ] **Step 6: Commit**

```bash
git add site/guide/ site/zh/guide/
git commit -m "docs(site): decompose core-concepts into design-system and per-topic pages"
```

---

### Task 5: 清理各页的实现细节

**Files:**
- Modify: `site/guide/execution.md`
- Modify: `site/guide/workspace-isolation.md`
- Modify: `site/guide/trend-analysis.md`
- Modify: `site/guide/configuration.md`（如有残留实现细节）
- Modify: `site/guide/evaluation.md`（如有残留实现细节）
- Modify: `site/guide/decision.md`（如有残留实现细节）
- 以及对应中文版

> **Codex review 补充：** 不仅 execution/workspace/trend 三页有实现细节，configuration、evaluation、decision 页也散布有 Python/TS 代码片段和 contract test 细节。本 Task 应扫描所有 guide 页，统一清理。

- [ ] **Step 1: execution.md — 去掉实现细节**

去掉或大幅精简以下内容：
- asyncio semaphore 细节 → 替换为"micro-eval 会自动并发执行 cells，你可以通过 `guardrails.max_concurrency` 控制并行数"
- 内部 RunCell 生命周期 → 精简为"每个 cell 会：准备 workspace → 运行 agent → 收集输出 → 验证 → 评分 → 清理"

保留的用户可见内容：
- 矩阵展开的概念和示例
- 执行顺序（确定性 vs 随机化）
- 结果存储位置（`.micro-eval/runs/`）
- 超时和 guardrails 配置

- [ ] **Step 2: workspace-isolation.md — 去掉 provider 内部细节**

去掉：
- Seatbelt/Bubblewrap 的具体系统调用描述
- Provider fallback 的内部逻辑

保留：
- 为什么起点一致很重要（设计原则）
- 三种 workspace type（blank/files/git_repo）的用法
- 四种隔离级别（logical/os_policy/container/vm）的配置方式
- SameStartSnapshot 概述和 caveat 行为

- [ ] **Step 3: trend-analysis.md — 去掉 SQLite 内部结构**

去掉：
- SQLite index 的表结构和存储细节
- `run_store.finalize_run` 的内部调用

保留：
- 趋势查询的用法（CLI 和 UI）
- Drift breakpoint 的概念和用户可见行为
- import 命令

- [ ] **Step 4: 扫描其他 guide 页的残留实现细节**

在 configuration.md、evaluation.md、decision.md 中搜索以下模式并清理：
- Python/TypeScript 代码片段（`asyncio`、`subprocess`、`Pydantic`、`zod`、`vitest`）
- 内部函数/类名引用（`build_decision`、`recomputeDecision`、`AnnotationPanel` 等）
- contract test 描述

保留用户可配置的 YAML 示例和 JSON 输出示例——这些是用户需要看的。

- [ ] **Step 5: 对中文版做同样的清理**

- [ ] **Step 6: Commit**

```bash
git add site/guide/ site/zh/guide/
git commit -m "docs(site): remove implementation details from user guide pages"
```

---

### Task 6: 各使用页添加上下文锚定

**Files:**
- Modify: `site/guide/configuration.md`
- Modify: `site/guide/tasks.md`
- Modify: `site/guide/evaluation.md`
- Modify: `site/guide/decision.md`
- 以及对应中文版

每个"使用"页的开头应该用 1-2 句话锚定到 Design System，告诉用户"你在决策闭环的哪个位置"。

- [ ] **Step 1: configuration.md 开头加锚定**

```markdown
::: tip Where you are in the decision loop
A **Configuration** is one column in the result matrix — it defines
*what you are testing*. See [Design System](./design-system#core-objects)
for how configurations relate to the other core objects.
:::
```

- [ ] **Step 2: tasks.md 开头加锚定**

```markdown
::: tip Where you are in the decision loop
A **Task** is one row in the result matrix — it defines *what to test*.
See [Design System](./design-system#core-objects) for the full picture.
:::
```

- [ ] **Step 3: evaluation.md 和 decision.md 同样处理**

- [ ] **Step 4: 中文版同步**

- [ ] **Step 5: Commit**

```bash
git add site/guide/ site/zh/guide/
git commit -m "docs(site): add design-system anchors to usage guide pages"
```

---

### Task 7: 更新入口页链接

**Files:**
- Modify: `site/guide/index.md`
- Modify: `site/guide/getting-started.md`
- Modify: `site/zh/guide/index.md`
- Modify: `site/zh/guide/getting-started.md`

- [ ] **Step 1: index.md — 更新 Next Steps**

当前指向 Getting Started。改为：
```markdown
## Next Steps

- [Getting Started](/guide/getting-started) — install and run your first comparison in 10 minutes
- [Design System](/guide/design-system) — understand the core principles before diving into configuration
```

- [ ] **Step 2: getting-started.md — 更新末尾**

在 Getting Started 末尾的 "Next Steps" 或 "What's Next" 部分，指向 Design System 作为下一步阅读。

- [ ] **Step 3: 中文版同步**

- [ ] **Step 4: Commit**

```bash
git add site/guide/ site/zh/guide/
git commit -m "docs(site): update entry page links to include design-system"
```

---

### Task 8: 最终验证

- [ ] **Step 1: 本地启动文档站点，逐页检查**

```bash
cd site && npm run dev
```

验证：
- 所有 sidebar 链接可点击
- Design System 页在 "Get Started" 组中正确显示
- core-concepts 跳转页工作正常
- 中文版 sidebar 和链接对应正确

- [ ] **Step 2: 全站链接和 anchor 扫描**

不仅搜索 `core-concepts`，还要扫描 reference 页中指向 guide 页的 anchor 链接：

```bash
# 扫描所有指向 core-concepts 的链接（英文和中文）
grep -rn "core-concepts" site/ --include="*.md"

# 扫描 reference 页中所有指向 guide 的链接，检查 anchor 是否仍然存在
grep -rn "/guide/" site/reference/ --include="*.md"
grep -rn "/guide/" site/zh/reference/ --include="*.md"
```

对每个找到的链接，验证目标页面上对应的 heading anchor 仍然存在。Task 5 删除/改写的内容（如 execution 的 "Trace Capture" 段、trend 的 SQLite 段）可能导致 reference 页中的 anchor 链接失效——这些需要更新。

- [ ] **Step 3: 中英文对称性检查**

```bash
# 比较英文和中文 guide 的文件列表
diff <(ls site/guide/*.md | sed 's|site/guide/||') <(ls site/zh/guide/*.md | sed 's|site/zh/guide/||')
```

确认：
- 英文有的页面中文都有
- 中文 sidebar 条目与英文条目一一对应
- 中文版的 heading anchor（如 `#core-objects`）与英文版一致（VitePress 自动从 heading 生成 anchor，中文 heading 会产生不同 anchor——需要用显式 `{#anchor}` 语法保持一致）

- [ ] **Step 4: 术语一致性检查**

确认 design-system.md 中定义的核心对象名称在所有页面中一致使用：
- "Cell" 不应在某些页叫 "RunCell"（RunCell 是代码层名称，用户文档统一用 Cell）
- "Evidence" 不应在某些页叫 "Evidence Chain"（design-system 用 Evidence，decision 可以用 Evidence Chain 作为完整链的称呼，但要一致）
- DecisionStatus 的 6 个值在 design-system 和 decision.md 中必须完全一致
- Run 和 ResultMatrix 在 design-system 和 execution（Running & Results）中定义一致

- [ ] **Step 5: Final commit**

```bash
git add site/
git commit -m "docs(site): final verification pass for documentation restructure"
```

---

## Part 3: 不在本次范围内

| 项目 | 理由 |
|------|------|
| 内部开发文档重组（Unicorn、engineering guidelines、CLAUDE.md） | 服务不同受众，是独立的工作项 |
| 新增 Examples | 当前 3 个 examples 已按场景组织，与本次结构重组无关 |
| Reference 页面内容修改 | 参考手册是查找型文档，结构已合理 |
| README.md / README.zh-CN.md 更新 | 可能需要更新站点链接，但属于跟进项 |
| 站点视觉设计或主题改动 | 与信息架构重组正交 |
