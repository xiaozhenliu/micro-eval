# CLAUDE.md

**Critical Rule**: 

- Always reply the user in Simplified Chinese. 
- git commit messages should be in English
- comments in any coding scripts should be in English 
- 禁止使用 TDD 方法：不要采用“先写失败测试，再写实现让测试通过”的开发流程。

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 分支与来源入口

- 日常实现、治理和 release preparation 只发生在 `dev`。
- `main` 是经过验证的公开投影；不要在 `main` 上开展源代码开发，也不要在当前 `dev` worktree 手工 merge 或切换到 `main` 发布。
- `dev` → `main` 只能使用 `scripts/release-to-main.sh`；发布边界和验证清单以 `docs/engineering/release-process.md` 及开发环境提供的 release skill 为准。
- [AGENTS.md](AGENTS.md) 是仓库级 branch、发布与安全 guardrail；本文件只补充 Claude Code 使用的项目上下文。
- [VERSION](VERSION) 是当前版本唯一人工编辑源；[CHANGELOG.md](CHANGELOG.md) 是 release-facing 变更记录；[TODOS.md](TODOS.md) 是 `dev` 上唯一的 unfinished-work Work Register。
- Work Register、local ticket、GitHub Issue、triage 与 completion evidence 的权威契约见 [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md) 和 [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md)。

## 开发方法硬规则

- 禁止使用 TDD 方法。开发顺序必须是：先理解规格与用户路径，再做模块/文件架构设计，再实现可运行的垂直切片，最后用测试和真实产物做验证。
- 测试只能作为验收、回归和契约保护手段，不能作为需求来源；不要为了让测试通过而缩窄实现范围。
- 如果外部 skill、工具或自动化建议使用 TDD，必须以本文件为准：禁止使用 TDD 方法。

## Work tracking

- 在 `dev` 上，任何 behavior、schema、security、release 或 multi-file change 都必须先在 [TODOS.md](TODOS.md) 登记，并链接一个且仅一个 `LOCAL-<EFFORT>-<NN>` ticket 或 `GH-<number>` Issue；详情只写在权威 ticket/Issue 中。
- 一文件 typo、纯格式调整或同等 trivial documentation correction 可不建 ticket；拿不准时遵循 ticket-first。
- Local ticket 默认放在私有 work-record directory；确实需要公开反馈或协作时才使用 GitHub Issue。`Triage`、`Executor` 与生命周期 `Status` 不得混为一个字段。
- 完成后记录 completion evidence，从 `TODOS.md` 移除，并将 release-facing 事实放入 `CHANGELOG.md` 或将实现验证放入 development log。

## 项目意图(来自 BRD + Unicorn Design)

`micro-eval` 是面向 1–20 人 AI 小团队的 **Agent / Skill 评测决策工具**。核心命题：将"我觉得这个 agent 更强"转化为可量化、可溯源、可复现的结论。

核心数据模型：`Run = Tasks × Configurations × Repetitions → ResultMatrix`

成功标准：用户能在 10 分钟内完成 配置 Configurations → 定义 Tasks → 发起 Run → 在矩阵对比中得出结论。

## 架构约束(实现时必须遵守)

这些约束来自 Unicorn Design + BRD,是后续所有技术决策的边界,**违背它们就偏离了产品定位**:

1. **执行层自写,评分/观测委托外部**。
   - **自写执行层** = agent subprocess 编排、并行执行、超时、隔离(git worktree)、结果收集。~100 行 Python,完全可控。
   - **DeepEval** = 评分库(custom metric + GEval/LLM-as-judge 单轮评分（已实现，v0.2.0）+ ConversationSimulator 多轮会话评测（v0.4 计划中）),不用其 test runner。会话评测通过 `model_callback` 桥接 micro-eval 的执行层,是单轮 judge 的并行路径(provider: `deepeval_conversational`),不替代默认行为。
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
6. **MVP 不做**：RBAC/SSO、复杂审计、大规模任务库、高级推荐引擎。
   v0.4 新增：可信内网多成员共享 Server（workspace 隔离、串行队列、只读模板库、归属记录），不含认证/权限控制。

## 核心领域模型

Unicorn Design 定义的对象及其关系(实现数据层时以此为准,详见 `docs/superpowers/specs/2026-06-02-unicorn-design.md` 第 3 节):

- **Configuration** → 结果矩阵的"列"：Agent × Skill(可选) × Environment × Params × Repetitions。
- **AgentSpec** → 被评测的完整程序(command + input_mode + output_mode + timeout)。
- **SkillSpec** → 挂载到 Agent 的能力单元(path + version)。
- **Task** → 评测单元(prompt + workspace + expectations + validation + scoring rubric)。可选会话评测字段：scenario(会话场景) + expected_outcome(期望结果) + user_description(模拟用户描述),映射 DeepEval ConversationalGolden。
- **WorkspaceSpec** → 执行环境(git_repo/blank/files + setup_commands + resource_limits)。
- **Run** → Tasks × Configurations × Repetitions 的一次执行,产出 ResultMatrix。
- **RunResult** → 一个 (Task, Configuration, Repetition) 的结果(scores + trace + cost + artifacts)。

关键基数关系:`Run` 在 `Tasks × Configurations × Repetitions` 的笛卡尔积上产生 ResultMatrix,对比页是这个矩阵的可视化。

## 路线图(决定动手顺序)

底座**串行接入**,不要并行做完(风险:执行链路过长):

- **Phase 1 (MVP)**:Configuration/Task/Run + 自写执行层 + 分层评分(validation → LLM judge) + 矩阵对比页 + Next.js 本地 UI。
- **Phase 2(已完成,v0.2.0)**:Langfuse trace 接入 + 复盘页 + 成本分析 + repetitions 统计聚合 + LLM judge。
- **Phase 3（已完成，v0.3.0）**：provider 化 sandbox（本地 OS 策略 Seatbelt/Bubblewrap + 远程 E2B/Modal，**不用本地 Docker**，见 spec §3.4.5）+ 更复杂 workspace 类型（多源 fixture + toolchain 指纹）+ 趋势分析（SQLite 索引 + drift breakpoint）。实施计划见 `docs/superpowers/plans/2026-06-14-phase3-implementation-plan.md`。

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
| 会话评测集成 | DeepEval ConversationSimulator 作为 Python import（不封装为 A2A 服务）；model_callback 桥接执行层；A2A 仅用于 agent-to-agent transport | DeepEval/AgentBeats 调研 + 设计评审 |
| 多轮 agent 通信 | subprocess 保持存活 + JSONL stdin/stdout 逐轮通信；复用现有 command + 安全边界 | 设计评审 2026-06-20 |

## 技术栈

- Python 3.11+ / uv — CLI + 评测引擎
- Typer — CLI 框架
- DeepEval — 评分库(custom metric, GEval 单轮 judge, ConversationSimulator 多轮评测)
- Langfuse Python SDK — 可选,cost 数据
- Next.js + TypeScript — 本地 Web UI
- pytest — Python 测试
- vitest — UI 测试

## Agent skills

### Issue tracker

Work tracking uses one `TODOS.md` Work Register and durable local Markdown
tickets by the contract in `docs/agents/issue-tracker.md`.

### Triage labels

Triage roles are separate from ticket lifecycle status and executor. See `docs/agents/triage-labels.md`.

### Domain docs

Domain documentation uses a single-context layout. See `docs/agents/domain.md`.

## Engineering guidelines routing

不要默认读取整个 `docs/engineering/` 目录。只有任务命中下列场景时，才读取对应文件：

- 架构边界、模块归属、跨模块依赖 → 读 `docs/engineering/architecture-guardrails.md`
- 实施设计、模块接口、迁移分期、store/adapter/evidence 落地 → 读 `docs/engineering/implementation-principles.md`
- Python CLI / engine / schema / subprocess → 读 `docs/engineering/python-guidelines.md`
- Next.js / TypeScript / zod / API route / UI data access → 读 `docs/engineering/frontend-guidelines.md`
- 测试计划、contract tests、flaky 控制 → 读 `docs/engineering/testing-guidelines.md`
- ResultMatrix、Decision、Artifact/Evidence 展示 → 读 `docs/engineering/ux-guidelines.md`
- secrets、workspace、subprocess 安全、网络边界 → 读 `docs/engineering/security-guidelines.md`
- 发布、版本号 bump、tag、dev→main 投影 → 必须先读 `docs/engineering/release-process.md`，并按 `.codex/skills/micro-eval-release/SKILL.md` 的清单逐步执行；发布脚本唯一副本在 `scripts/release/` 与 `scripts/release-to-main.sh`
- 不确定该读哪个工程规范 → 只读 `docs/engineering/README.md`

**安全规范例外于上面的按需路由**：`docs/engineering/security-guidelines.md` 是 cross-cutting 规范，不受"命中场景才读"约束。任何开发里程碑 / vertical slice（涉及 subprocess 调用、env 注入、stdout/stderr 捕获、artifact 持久化、workspace 写入的，几乎覆盖所有执行层改动）在动手前都必须读它，完成后必须逐条过它末尾的「Code Review Checklist」，并在交付报告中说明 secrets redaction、workspace 边界、shell interpolation 三项的处理方式。安全要求与功能需求同级，不是加分项。

硬规则：
- 每个开发里程碑都必须满足 `docs/engineering/security-guidelines.md`。安全验收与功能验收同为合并门槛：未通过其 Code Review Checklist 的改动不得合并到 main，即使功能测试全绿。
- 长期架构权威来源：`docs/superpowers/specs/2026-06-02-unicorn-design.md` Part I。
- 当前 MVP 范围权威来源：`docs/superpowers/specs/2026-06-02-mvp-profile.md`。
- 测试架构权威来源：`docs/superpowers/specs/2026-06-02-test-architecture.md`。
- 工程规范不能重新定义 schema 字段、模块契约或 MVP 范围。
- 如果工程规范与上述权威来源冲突，先更新权威来源，再更新工程规范。

## 常用开发命令

完整命令和验证矩阵见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)。

```bash
# Python CLI
uv run micro-eval run --config eval.yaml
uv run pytest

# Next.js UI
cd ui && npm run dev
cd ui && npx vitest run
```
