# AGENTS.md

**Critical Rule**: Always reply the user in Simplified Chinese. 

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 分支策略

- **main** — 干净的发布分支，只包含源码、文档、测试。不跟踪 AGENTS.md、BRD、PRD。
- **dev** — 日常开发分支，包含 main 的所有内容 + AGENTS.md、micro-eval-brd.md、micro-eval-prd.md。

**日常工作流：**
1. 在 `dev` 分支上开发（当前分支）
2. 功能完成后 merge 到 `main`（main 的 .gitignore 会自动排除 AGENTS.md/BRD/PRD）
3. 不要直接在 main 上开发

## 当前状态

v0.1.0 MVP 已完成。Python CLI + Next.js 本地 Web UI 均可运行。25 个 pytest 测试通过。

## 项目意图(来自 PRD)

`micro-eval` 是面向 1–20 人 AI 小团队**的 **Agent / Skill 评测助手**。它不重新造平台,而是把三个现成底座拼成一套"能真正用起来"的评测工作台,把"我觉得这个 agent 更强"变成"它在哪些任务上更强、为什么、成本多少、值不值得继续投"。

成功标准(MVP):用户能在 10 分钟内完成 建项目 → 导任务 → 配多个 agent/skill 版本 → 发起 run → 看对比/trace/成本 → 得出结论。

## 架构约束(实现时必须遵守)

这些约束来自 PRD,是后续所有技术决策的边界,**违背它们就偏离了产品定位**:

1. **执行层自写,评分/观测委托外部**。
   - **自写执行层** = agent subprocess 编排、并行执行、超时、隔离(git worktree)、结果收集。~100 行 Python,完全可控。
   - **DeepEval** = 仅作评分库(custom metric + 未来 GEval/LLM-as-judge),不用其 test runner。
   - **Langfuse** = 观测层(可选):trace、cost/latency 统计。未配置时降级运行。
   - **OpenHands** = Phase 3 真实任务执行层(MVP 不接入)。
   - 对外部底座保留**适配层**——底座迭代快,变化吸收在适配层内。
2. **四层分层**(代码组织应能映射到这四层):
   - 资产层:管理 prompts / skills / tasks / rubrics / evaluation presets,可对接 PromptHub、Git repo、本地 Markdown、手工录入。
   - 执行层:调用上述三个底座跑实验。
   - 控制层(**产品核心**):建项目、组织任务集、配 agent/skill/model、设环境、发起 run、收集结果、出报告。
   - 展示层:对比页 / trace 页 / run 列表 / 报告页 / 配置页。
3. **同起点优先(P3)**:每次 run 必须有明确、可复现的起点(workspace 状态、repo commit、skill 版本、工具白名单、sandbox 配置、上下文预算)。环境不一致 = 结果不可信,这是产品要解决的头号痛点。
4. **可解释优先(P4)**:任何结论都要能回溯到 task、trace、diff、cost。设计数据模型与 UI 时始终保留这条溯源链。
5. **先人工后自动(P5)**:MVP 评分以人工为主,自动评分逐步增强。不要一上来就堆自动评分引擎。
6. **MVP 不做**:多团队协作、RBAC/SSO、复杂审计、大规模任务库、高级推荐引擎。聚焦最常见的"对比 + 复盘"场景。

## 核心领域模型

PRD 定义的对象及其关系(实现数据层时以此为准,字段细节见 `micro-eval-prd.md` 第 5 节):

- **Project** → 一类评测目标,拥有多个 Task 与多次 Run。
- **Task** → 可重复运行的测试单元(含 input_payload、expected_output、rubric、business_impact_tier)。
- **Skill** → 可切换、可版本化的能力单元(name + version + parameters + dependencies)。
- **AgentConfig** → 一个运行组合(model + routing + toolset + skills_profile + 采样参数)。
- **Run** → 对某任务集的一次实际执行(异步,记录 status / cost / trace_bundle_ref)。
- **RunResult** → 一个 `task × agent` 的结果(score / pass_fail / diff_ref / trace_ref / failure_mode)。
- **EvaluationPreset** → 把常复用的 promptfoo_config / langfuse_project / openhands_profile 打包。

关键基数关系:`Run` 在 `任务集 × AgentConfig` 的笛卡尔积上产生多条 `RunResult`,对比页正是这个结果矩阵的可视化。

## 路线图(决定动手顺序)

按 PRD,底座**串行接入**,不要并行做完(风险:执行链路过长):

- **Phase 1 (MVP)**:project/task/run + 自写执行层 + DeepEval 评分 + 基础对比页 + 静态 HTML 报告 + Next.js 本地 UI。
- **Phase 2**:Langfuse trace 接入 + 复盘页 + 成本分析 + skill profile 对比。
- **Phase 3**:OpenHands sandbox 接入 + 更复杂任务类型 + 趋势分析。

完整需求见 `micro-eval-prd.md`(产品规格)与 `micro-eval-brd.md`(商业背景)。

## 已锁定的技术决策(来自工程评审 2026-05-31)

| 决策 | 结论 | 来源 |
|------|------|------|
| 评测引擎 | 自写执行层,DeepEval 仅作评分库 | Codex outside voice + 用户确认 |
| Input 传递 | stdin/文件传参,禁止 shell 字符串插值 | Codex outside voice + 用户确认 |
| Workspace 隔离 | git worktree(要求项目在 git repo 中） | 用户选择 |
| 执行模式 | baseline/candidate 并行执行(asyncio) | 用户确认 |
| 数据契约 | Pydantic(Python) + zod(TS) 共享 schema | 用户确认 |
| 测试策略 | pytest 单元测试 + E2E 集成测试 | 用户确认 |
| Web UI | Next.js 本地 Web UI,API routes 读取 .micro-eval/ JSON | 设计文档 |

## 技术栈

- Python 3.11+ / uv — CLI + 评测引擎
- Typer — CLI 框架
- DeepEval — 评分库(custom metric, 未来 GEval)
- Langfuse Python SDK — 可选,cost 数据
- Next.js + TypeScript — 本地 Web UI
- pytest — Python 测试
- vitest — UI 测试

## 开发命令(待项目骨架建立后补充)

```bash
# Python CLI
uv run micro-eval run --baseline X --candidate Y
uv run pytest

# Next.js UI
cd ui && npm run dev
cd ui && npx vitest run
```

## gstack 项目路径

设计文档与评审产物存放在：`~/.gstack/projects/micro-eval/`

关键文件：
- 设计文档：`~/.gstack/projects/micro-eval/xz-main-design-20260530-222345.md`
- 工程评审测试计划：`~/.gstack/projects/micro-eval/xz-main-eng-review-test-plan-20260531-120000.md`
- 实现任务清单：`~/.gstack/projects/micro-eval/tasks-eng-review-*.jsonl`

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
