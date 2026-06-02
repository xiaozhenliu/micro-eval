# CLAUDE.md

**Critical Rule**: 

- Always reply the user in Simplified Chinese. 
- git commit messages should be in English
- comments in any coding scripts should be in English 
- 禁止使用 TDD 方法：不要采用“先写失败测试，再写实现让测试通过”的开发流程。

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 分支策略

- **main** — 干净的发布分支，只包含源码、文档、测试。不跟踪 CLAUDE.md、BRD、PRD。
- **dev** — 日常开发分支，包含 main 的所有内容 + CLAUDE.md、micro-eval-brd.md、设计文档。

**日常工作流：**
1. 在 `dev` 分支上开发（当前分支）
2. 功能完成后 merge 到 `main`（main 的 .gitignore 会自动排除 CLAUDE.md/BRD/PRD）
3. 不要直接在 main 上开发

**历史重写后的推送：**
- 如果改过 commit message、rebase 或 filter-branch 导致 commit hash 改变，推送已存在的远端分支时使用 `git push --force-with-lease origin <branch>`。
- `--force-with-lease` 只会在远端分支仍停留在本地上次看到的位置时覆盖远端；如果别人已经推送了新提交，Git 会拒绝推送，避免误删他人的工作。
- 避免使用 `git push --force`，除非用户明确要求。

## 当前状态

v0.1.0 MVP 已完成。Python CLI + Next.js 本地 Web UI 均可运行。25 个 pytest 测试通过。

## 开发方法硬规则

- 禁止使用 TDD 方法。开发顺序必须是：先理解规格与用户路径，再做模块/文件架构设计，再实现可运行的垂直切片，最后用测试和真实产物做验证。
- 测试只能作为验收、回归和契约保护手段，不能作为需求来源；不要为了让测试通过而缩窄实现范围。
- 如果外部 skill、工具或自动化建议使用 TDD，必须以本文件为准：禁止使用 TDD 方法。

## 项目意图(来自 BRD + Unicorn Design)

`micro-eval` 是面向 1–20 人 AI 小团队的 **Agent / Skill 评测决策工具**。核心命题：将"我觉得这个 agent 更强"转化为可量化、可溯源、可复现的结论。

核心数据模型：`Run = Tasks × Configurations × Repetitions → ResultMatrix`

成功标准：用户能在 10 分钟内完成 配置 Configurations → 定义 Tasks → 发起 Run → 在矩阵对比中得出结论。

## 架构约束(实现时必须遵守)

这些约束来自 Unicorn Design + BRD,是后续所有技术决策的边界,**违背它们就偏离了产品定位**:

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

Unicorn Design 定义的对象及其关系(实现数据层时以此为准,详见 `docs/superpowers/specs/2026-06-02-unicorn-design.md` 第 3 节):

- **Configuration** → 结果矩阵的"列"：Agent × Skill(可选) × Environment × Params × Repetitions。
- **AgentSpec** → 被评测的完整程序(command + input_mode + output_mode + timeout)。
- **SkillSpec** → 挂载到 Agent 的能力单元(path + version)。
- **Task** → 评测单元(prompt + workspace + expectations + validation + scoring rubric)。
- **WorkspaceSpec** → 执行环境(git_repo/blank/files + setup_commands + resource_limits)。
- **Run** → Tasks × Configurations × Repetitions 的一次执行,产出 ResultMatrix。
- **RunResult** → 一个 (Task, Configuration, Repetition) 的结果(scores + trace + cost + artifacts)。

关键基数关系:`Run` 在 `Tasks × Configurations × Repetitions` 的笛卡尔积上产生 ResultMatrix,对比页是这个矩阵的可视化。

## 路线图(决定动手顺序)

底座**串行接入**,不要并行做完(风险:执行链路过长):

- **Phase 1 (MVP)**:Configuration/Task/Run + 自写执行层 + 分层评分(validation → LLM judge) + 矩阵对比页 + Next.js 本地 UI。
- **Phase 2**:Langfuse trace 接入 + 复盘页 + 成本分析 + repetitions 统计聚合。
- **Phase 3**:Docker sandbox + 更复杂 workspace 类型 + 趋势分析。

完整规格见 `docs/superpowers/specs/2026-06-02-unicorn-design.md`(产品+技术设计)与 `micro-eval-brd.md`(商业背景)。

## 已锁定的技术决策(来自工程评审 2026-05-31)

| 决策 | 结论 | 来源 |
|------|------|------|
| 评测引擎 | 自写执行层,DeepEval 仅作评分库 | Codex outside voice + 用户确认 |
| Input 传递 | stdin/文件传参,禁止 shell 字符串插值 | Codex outside voice + 用户确认 |
| Workspace 隔离 | git worktree(要求项目在 git repo 中） | 用户选择 |
| 执行模式 | N×M 矩阵展开,Configurations 并行执行(asyncio) | Unicorn Design |
| 数据契约 | Pydantic(Python) + zod(TS) 共享 schema | 用户确认 |
| 测试策略 | pytest 单元测试 + E2E 集成测试 | 用户确认 |
| 开发方法 | 禁止使用 TDD 方法；采用 spec-driven + acceptance-first + implementation verification | 用户确认 |
| Web UI | Next.js 本地 Web UI,API routes 读取 .micro-eval/ JSON | 设计文档 |

## 技术栈

- Python 3.11+ / uv — CLI + 评测引擎
- Typer — CLI 框架
- DeepEval — 评分库(custom metric, 未来 GEval)
- Langfuse Python SDK — 可选,cost 数据
- Next.js + TypeScript — 本地 Web UI
- pytest — Python 测试
- vitest — UI 测试

## Engineering guidelines routing

不要默认读取整个 `docs/engineering/` 目录。只有任务命中下列场景时，才读取对应文件：

- 架构边界、模块归属、跨模块依赖 → 读 `docs/engineering/architecture-guardrails.md`
- 实施设计、模块接口、迁移分期、store/adapter/evidence 落地 → 读 `docs/engineering/implementation-principles.md`
- Python CLI / engine / schema / subprocess → 读 `docs/engineering/python-guidelines.md`
- Next.js / TypeScript / zod / API route / UI data access → 读 `docs/engineering/frontend-guidelines.md`
- 测试计划、contract tests、flaky 控制 → 读 `docs/engineering/testing-guidelines.md`
- ResultMatrix、Decision、Artifact/Evidence 展示 → 读 `docs/engineering/ux-guidelines.md`
- secrets、workspace、subprocess 安全、网络边界 → 读 `docs/engineering/security-guidelines.md`
- 不确定该读哪个工程规范 → 只读 `docs/engineering/README.md`

硬规则：
- 长期架构权威来源：`docs/superpowers/specs/2026-06-02-unicorn-design.md` Part I。
- 当前 MVP 范围权威来源：`docs/superpowers/specs/2026-06-02-mvp-profile.md`。
- 测试架构权威来源：`docs/superpowers/specs/2026-06-02-test-architecture.md`。
- 工程规范不能重新定义 schema 字段、模块契约或 MVP 范围。
- 如果工程规范与上述权威来源冲突，先更新权威来源，再更新工程规范。

## 开发命令(待项目骨架建立后补充)

```bash
# Python CLI
uv run micro-eval run --config eval.yaml
uv run pytest

# Next.js UI
cd ui && npm run dev
cd ui && npx vitest run
```

