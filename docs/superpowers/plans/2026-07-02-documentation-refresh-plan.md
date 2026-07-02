# Documentation Refresh Plan (v0.4.1 对齐)

> **For agentic workers:** 每个 Task 由一个独立 subagent 执行。Task 之间文件集完全不相交，可并行。执行者只做文档编辑，**不 commit、不 push**——主会话统一 review 后提交。

**Goal:** 把全项目文档从 v0.4.0/更早的滞留状态对齐到 v0.4.1 实况（权威版本号来自 `VERSION` 文件）。

**Architecture:** 5 个互不相交的文档域并行修复：README 双语、site 文档站（中英）、specs 设计文档、DEVELOPMENT.md + engineering 规范、plans/bug_reports 状态标注。

**审计依据:** 2026-07-02 五路并行审计（本会话），逐条发现见各 Task。

## Global Constraints（所有 Task 共同遵守）

- 权威版本号 = `VERSION` 文件内容 = **0.4.1**。
- 简体中文文档用简体中文，英文文档用英文；代码注释/commit message 英文。
- **不要 commit、不要 push**，只编辑文件。
- 不得改动任何源码、测试、schema 文件；本计划只改 markdown/config.ts（sidebar）。
- 编辑前先 Read 目标文件确认行号仍准确（审计与执行之间可能有偏移）。
- 文档带 frontmatter 的（`updated_at` 等字段），更新内容时同步更新 `updated_at: 2026-07-02`（保持该文件原有时间格式）。

## Ground Truth（执行者不了解项目历史，以此为准）

- 版本链：v0.3.0（Phase 3：sandbox providers Seatbelt/Bubblewrap/E2B/Modal、SQLite 索引+趋势分析）→ v0.3.1–0.3.5 → **v0.4.0 Team Server**（serve/worker/workspace/template/queue 子命令，workspace 隔离、串行队列、只读模板库、归属记录）→ **v0.4.1 Conversational Evaluation**（当前）。
- CLI 全量 13 个子命令：`init` `validate` `run` `list` `report` `apply-evaluation` `ui` `build-plan` `serve` `worker` `workspace` `template` `queue`。
- 测试规模：**517 pytest + 42 vitest**。
- Conversational Evaluation 关键事实：
  - judge provider 新增 `deepeval_conversational`（`src/micro_eval/models/configuration.py` `provider: Literal["deepeval", "deepeval_conversational"]`）。
  - TaskSpec 新增三个可选字段：`scenario`、`expected_outcome`、`user_description`（`src/micro_eval/models/task.py:133-135`），映射 DeepEval `ConversationalGolden`；三者均空则走单轮路径。
  - 执行链：`src/micro_eval/engine/agent_bridge.py`（`SubprocessBridge`，JSONL stdin/stdout 逐轮通信，进程会话期保活，保留 workspace 隔离/SIGTERM timeout/env whitelist/secrets redaction）→ `src/micro_eval/evaluation/conversational_judge.py` 两阶段 `simulate_conversation()` → `score_conversation()`；kernel 分支在 `engine/kernel.py`（`plan.judge.provider == "deepeval_conversational"` 时走 `_execute_cell_conversational`）。
  - 5 个核心 metric：`conversation_completeness`、`turn_relevancy`、`knowledge_retention`、`role_adherence`、`goal_accuracy`，另有 ConversationalGEval 自定义评分。
  - 证据：`conversational_judge` 类型 EvidenceItem；CellResult 增加 `conversation_ref` 指向 `conversation.json` 产物。
  - 示例：`examples/conversational-eval/`。
- UI 实际组件（`ui/src/components/`）：`MatrixHeatmap.tsx`（**不存在** `ResultMatrix`）、`AnnotationPanel.tsx`（**不存在** `EvaluationPanel`）、`RunList` `CellDetail` `TraceViewer` `ComparisonTable` `ConfigEditor` `CostPanel` `DecisionSummary` 及 v0.4 的 `WorkspaceCard` `QueueDashboard` `MemberBadge` `QueueJobCard` `RunEnqueueButton` `TemplateCard`。
- `src/micro_eval/engine/providers/`：`base.py`、`os_policy.py`（Seatbelt/Bubblewrap，含 network_policy 强制）、`remote.py`（E2B/Modal）。
- `src/micro_eval/store/sqlite_store.py` 已存在（SQLite 索引，JSON 仍为 source of truth）。
- release 脚本现位于 `scripts/release/`（check-version-consistency.py、generate-dependency-inventory.py、sync-version.py、preflight-release.sh）；`.codex/skills/micro-eval-release/SKILL.md` 在当前分支已不存在；发布流程文档为 `docs/engineering/release-process.md`。
- CHANGELOG.md 是全项目最准确的版本记录（已到 0.4.1），可作为措辞参考。

---

### Task 1: README 双语 + docs/README.md

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/README.md`

**改动清单（README.md，README.zh-CN.md 做完全对应的中文同步）：**

- [ ] 版本徽章（约第 7 行）`version-0.4.0` → `version-0.4.1`；正文 `Current version: 0.4.0`（约第 10 行）→ `0.4.1`。
- [ ] 简介段（约第 16 行）：在现有 Phase 3 能力描述后补充 Team Server 与 Conversational Evaluation 一句话介绍（参考 CHANGELOG 0.4.0/0.4.1 条目措辞）。
- [ ] Features 列表（约 28–43 行）新增两条：
  - `**Team Server** — shared server for trusted LANs: per-member workspace isolation, serial run queue, read-only template library, attribution records (v0.4.0)`
  - `**Conversational evaluation** — multi-turn agent evaluation via DeepEval ConversationSimulator with a JSONL subprocess bridge; parallel path to the single-turn GEval judge (v0.4.1)`
- [ ] CLI Commands 表（约 107–115 行）：补齐缺失的 6 个命令 `build-plan` `serve` `worker` `workspace` `template` `queue`，每行一句话描述（从 `uv run micro-eval <cmd> --help` 或 `src/micro_eval/cli/` 源码提取，禁止杜撰）。
- [ ] Examples 段（约第 93 行）：补提 `examples/conversational-eval/`。
- [ ] 约第 226 行 `Phase 2 review surface` → 去掉阶段编号，改为功能性描述（如 `human review surface`）。
- [ ] 文末 metadata：`updated_at` 改为 2026-07-02。
- [ ] README.zh-CN.md 同步以上全部（注意其第 16 行还有 "0.3.3 新增…" 的旧措辞需要一并顺到 0.4.1）。
- [ ] docs/README.md：Key documents 表（约 50–52 行）在发布证据两行后补一行说明：最新版本记录见根目录 `CHANGELOG.md`（v0.3.0 起 release evidence 缺档，**不要**链接不存在的文件）。

**验证：** `grep -n "0\.4\.0" README.md README.zh-CN.md` 应只剩 CHANGELOG 式历史条目（如有）；`grep -c "serve" README.md` ≥1。

### Task 2: site/ 文档站（中英同步）

**Files:**
- Modify: `site/reference/cli.md` + `site/zh/reference/cli.md`
- Modify: `site/reference/task-yaml.md` + `site/zh/reference/task-yaml.md`
- Modify: `site/reference/eval-yaml.md` + `site/zh/reference/eval-yaml.md`
- Modify: `site/reference/api-routes.md` + `site/zh/reference/api-routes.md`
- Modify: `site/guide/getting-started.md` + `site/zh/guide/getting-started.md`
- Modify: `site/guide/evaluation.md` + `site/zh/guide/evaluation.md`
- Create: `site/guide/conversational-evaluation.md` + `site/zh/guide/conversational-evaluation.md`
- Modify: `site/.vitepress/config.ts`（sidebar）

**改动清单（每处英文改完立即做中文对应页同步；两语言页面保持章节结构一致）：**

- [ ] cli.md 第 3 行 `Current version: 0.4.0` → `0.4.1`；第 805 行示例输出 `# micro-eval 0.4.0` → `0.4.1`。
- [ ] cli.md 新增 `apply-evaluation` 命令章节：从 `src/micro_eval/cli/evaluate.py` 与 `uv run micro-eval apply-evaluation --help` 提取真实参数与用途（将 evaluation JSON 应用到 run 并重算 decision），按现有命令章节的格式写。
- [ ] task-yaml.md 字段表（约 50–74 行）：新增 `scenario` / `expected_outcome` / `user_description` 三个可选字段行，说明：均为 conversational evaluation 用，三者全空走单轮评测；`scenario` 非空时 task 可进入多轮路径。字段类型/默认值从 `src/micro_eval/models/task.py` 核对。
- [ ] eval-yaml.md 约第 361 行：`Currently only \`deepeval\` is supported` → 说明支持 `deepeval`（单轮 GEval）与 `deepeval_conversational`（多轮，v0.4.1），并链接到新的 conversational-evaluation 指南页。
- [ ] api-routes.md 约第 659 行示例 `"version": "0.4.0"` → `"0.4.1"`。
- [ ] getting-started.md 约第 52 行示例输出 `# micro-eval 0.3.2` → `# micro-eval 0.4.1`。
- [ ] guide/evaluation.md：在现有 Validation → Judge → Human 管线介绍后新增一小节 "Multi-turn conversational evaluation"，一段话概述 + 链接到新页。
- [ ] 新建 guide/conversational-evaluation.md（中英两份）。内容结构：
  1. What it is（ConversationSimulator 驱动多轮会话，是单轮 judge 的并行路径，不改默认行为）
  2. When to use（task 定义了 scenario/expected_outcome/user_description）
  3. How it works（两阶段 simulate→score；SubprocessBridge JSONL 协议一段简述：agent 进程保活，每轮 stdin 写 `{"turn": N, "content": "..."}`，stdout 读 `{"content": "..."}`；安全边界与单轮一致）
  4. Configuration（eval.yaml judge provider 设为 `deepeval_conversational`；task 三字段示例——从 `examples/conversational-eval/` 取真实 YAML 片段，禁止杜撰）
  5. Metrics（5 个核心 metric 列表 + ConversationalGEval）
  6. Output（`conversation.json` 产物、`conversational_judge` evidence、CellResult.conversation_ref）
  写作风格对齐现有 guide/team-server.md：面向用户、无内部实现细节（模块文件名不出现在正文，配置与产物为主）。
- [ ] config.ts：在 guide sidebar 的 Advanced 组（en + zh 两处 sidebar 定义）加入 conversational-evaluation 条目，位置放在 team-server 附近。

**验证：** `cd ui 不需要`；运行 `grep -rn "only \`deepeval\`" site/` 无结果；`grep -rn "0\.3\.2\|micro-eval 0\.4\.0" site/ | grep -v changelog` 无结果；若本机可行运行 `cd site && npm run build`（如 site 无独立 package 则跳过，说明即可）。

### Task 3: specs 设计文档

**Files:**
- Modify: `docs/superpowers/specs/2026-06-02-unicorn-design.md`
- Modify: `docs/superpowers/specs/2026-06-02-mvp-profile.md`
- Modify: `docs/superpowers/specs/2026-06-02-test-architecture.md`
- Modify: `docs/superpowers/specs/2026-06-19-team-server-design.md`
- Modify: `docs/superpowers/specs/2026-06-15-test-coverage-plan.md`

**改动清单：**

- [ ] unicorn-design.md §10（约 446–484 行）：整节重写为「Current State（v0.4.1，2026-07-02 更新）+ Historical: v0.1.0 legacy state（已全部迁移完成）」。新现状按 Ground Truth 写：argv-only subprocess、worktree 已接入主流程、canonical configurations[] 矩阵、annotation 持久化、Pydantic/zod golden 双端守护、GEval judge + conversational path、sandbox providers、SQLite 趋势、Team Server。原 v0.1.0 清单保留为折叠的历史小节并逐条标注"已于 vX.Y 解决"；迁移分期 M0–M4 全部标注已完成。
- [ ] unicorn-design.md §5.3 "Legacy risk"（约 225 行）：改为已解决（argv-only 已交付，v0.2.x），保留一句历史注记。
- [ ] unicorn-design.md §5.5 "Legacy gap"（约 251 行）：同上（worktree 已接入；snapshot 已含多源 fixture digest + toolchain fingerprint）。
- [ ] unicorn-design.md §5.6 "Legacy gap"（约 265 行）：annotation 已持久化，改为历史注记；同节 Future levels 中 Langfuse 标注"已实现（v0.2.0），LangSmith/OpenTelemetry 仍为 Future"。
- [ ] unicorn-design.md §5.7 Future levels（约 278 行）：把 pass@k/pass^k 从 Future 移入 "Implemented levels"（已在 `decision/aggregation.py` 实现）。
- [ ] unicorn-design.md §4（约 180–182 行）："当前 RunResult 只有 task_id + agent_name" 与 "Pydantic 与 zod 当前未完全对齐" 改为历史注记（现已对齐，golden + CI golden-sync 守护）。
- [ ] mvp-profile.md：frontmatter `status: active` → `status: superseded`，头部加一段注记：本文描述的 legacy v0.1.0 → MVP 迁移已于 v0.2.x 全部完成，保留作历史参考；§8 迁移表每行尾注"已完成"。
- [ ] test-architecture.md：frontmatter `updated` 改 2026-07-02；§2 表格"当前状态"更新为 517 pytest + 42 vitest（2026-07-02, v0.4.1）；§5 "当前状态 vs 目标"表（约 200、211 行）与 §5.1（215–218 行）的过时数字同步更新或标注为历史快照；§3.4（约 104 行）"shell 字符串插值当前仍存在、xfail" 改为已消除（argv-only，测试为回归守护）。
- [ ] team-server-design.md：frontmatter `status: draft` → `status: implemented`，加一行"已随 v0.4.0 交付（2026-06-19）"。
- [ ] test-coverage-plan.md：frontmatter `status: approved` → `status: completed`，头部注记：基线 v0.3.1/224 tests，已执行完毕，现规模 517 pytest + 42 vitest。

**约束：** 不改变任何架构契约表述（§2 不变量、§5 各模块 Responsibility/Owns、§6 Evidence 形状、§7 Gate 语义），只修"现状描述"类内容。

**验证：** `grep -n "create_subprocess_shell" docs/superpowers/specs/2026-06-02-unicorn-design.md` 剩余出现处均应位于明确的历史注记上下文中。

### Task 4: DEVELOPMENT.md + engineering 规范

**Files:**
- Modify: `docs/DEVELOPMENT.md`
- Modify: `docs/engineering/frontend-guidelines.md`
- Modify: `docs/engineering/ux-guidelines.md`
- Modify: `docs/engineering/security-user-run-guidelines.md`
- Modify: `docs/engineering/implementation-principles.md`

**改动清单：**

- [ ] DEVELOPMENT.md 约 105 行 cli/ 注释：补 `apply-evaluation`。
- [ ] DEVELOPMENT.md 约 107 行 engine/ 注释：补 `providers/`（Seatbelt/Bubblewrap/E2B/Modal）与 `agent_bridge.py`（JSONL multi-turn bridge）。
- [ ] DEVELOPMENT.md 约 118 行：`ResultMatrix` → `MatrixHeatmap`。
- [ ] DEVELOPMENT.md "Canonical 数据流"（约 122–131 行）：第 4 步后补一条分支说明：`judge.provider == "deepeval_conversational"` 时，kernel 走 conversational 分支——`SubprocessBridge`（JSONL 多轮）驱动 agent，`conversational_judge` 两阶段 simulate→score，产出 `conversation.json` + `conversational_judge` evidence；deterministic pass/fail 语义不被覆盖。
- [ ] DEVELOPMENT.md 第 15 行与约 201 行对 `.codex/skills/micro-eval-release/SKILL.md` 的引用：先确认该文件确不存在，然后改指 `docs/engineering/release-process.md` 与 `scripts/release/`（generate-dependency-inventory.py 的新路径）。
- [ ] frontend-guidelines.md 约 38、41 行：`ResultMatrix` → `MatrixHeatmap`，`EvaluationPanel` → `AnnotationPanel`；组件清单按 Ground Truth 的实际组件列表刷新（含 v0.4 team-server 组件）。
- [ ] ux-guidelines.md 约 44 行：`ResultMatrix` → `MatrixHeatmap`（保留"矩阵是核心界面"的语义）。
- [ ] security-user-run-guidelines.md 约 49–54 行 "Network and External Services"：改写为分层事实——Level 0（默认，无网络隔离）与 Level 1 OS 策略 provider（macOS Seatbelt / Linux Bubblewrap，支持 network_policy 强制，v0.3.0）以及远程 provider（E2B/Modal）；提及 provider 不可用时降级 Level 0 + caveat 的行为。措辞与 `docs/superpowers/specs/2026-06-02-unicorn-design.md` §5.5 和 `src/micro_eval/engine/providers/os_policy.py` 实际能力核对后再写，禁止夸大隔离保证。
- [ ] implementation-principles.md 约 49–51 行：SQLite 从"未来迁移目标"改为现状——`store/sqlite_store.py` 已作为索引层存在（JSON 仍是 source of truth），边界原则不变。

**验证：** `grep -rn "ResultMatrix\|EvaluationPanel" docs/ --include="*.md" | grep -v plans/ | grep -v _archive` 无结果；`grep -n "micro-eval-release/SKILL.md" docs/DEVELOPMENT.md` 无结果。

### Task 5: plans / bug_reports 状态标注

**Files:**
- Modify: `docs/superpowers/plans/2026-06-19-team-server-implementation-plan.md`
- Modify: `docs/superpowers/plans/2026-06-20-conversational-eval-plan.md`
- Modify: `docs/superpowers/plans/2026-06-15-issue1-decision-single-source.md`
- Modify: `docs/superpowers/plans/2026-06-15-documentation-restructure-plan.md`
- Modify: `docs/bug_reports/2026-06-03-mvp-readiness-review-findings.md`
- Modify: `docs/dev/README.md`

**改动清单（只加状态与注记，不逐个勾选 checkbox——未逐项验证的勾选是造假）：**

- [ ] team-server-implementation-plan.md：frontmatter `status: draft` → `status: implemented`；头部加注记："已随 v0.4.0 交付（2026-06-19，见 CHANGELOG）。checklist 未逐项回填，以代码与 CHANGELOG 为准。"
- [ ] conversational-eval-plan.md：frontmatter 补 `status: implemented`；同样注记（v0.4.1，2026-06-20）。
- [ ] issue1-decision-single-source.md：frontmatter 补 `status: completed`；注记：UI 侧 `recomputeDecision` 已删除（v0.3.4），`grep -rn recomputeDecision ui/src` 零结果。
- [ ] documentation-restructure-plan.md：先核实其 Step 4（术语一致性）与 Step 5（final commit）是否实际完成（检查 site/ 现状 + git log --oneline -- site/ 是否有对应提交）；已完成则补 `status: completed` + 注记；如有真实未完成项，在文档头部列出剩余项并标注 `status: partially-completed`，同时在完成报告中明确说明。
- [ ] 2026-06-03-mvp-readiness-review-findings.md：逐条核对 TODO 清单（如 TODO-3 runner.py/scorer.py 已删除，可 `find src -name runner.py -o -name scorer.py` 验证）；每条 TODO 后标注 `[resolved vX.Y]` 或 `[still open]`（必须逐条给出验证依据）；全部 resolved 则 frontmatter `status: active` → `status: resolved`，否则保留 active 并在头部汇总剩余项。
- [ ] docs/dev/README.md：把 decisions 目录 "future location" 措辞改为现状（该目录已有内容）。

**验证：** 各文件 frontmatter 均有明确 status；报告中列出每条 TODO 的核验结论。

---

## 明确不在本计划范围（需用户单独决策）

1. `docs/security/2026-06-20-security-audit.md`：未被 git 追踪，5 项发现（F1–F5）代码均未修复——是否纳入 git、是否排修复迭代，属代码/流程决策。
2. 补 v0.3.0–v0.4.1 的 release evidence、dependency inventory 与 git tag：需实际跑发布流程且打 tag 需用户批准。
3. 是否恢复 `.codex/skills/micro-eval-release/SKILL.md`（或以 `docs/engineering/release-process.md` 为唯一入口）：流程决策。
