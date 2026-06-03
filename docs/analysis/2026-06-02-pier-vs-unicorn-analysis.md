---
title: "Pier vs Unicorn (micro-eval) 对比分析"
date: 2026-06-02
status: 分析完成
type: competitive-analysis
subject: datacurve-ai/pier
scope: benchmark runner、任务格式、执行隔离、轨迹、复盘、统计、Viewer、与 Unicorn 模块映射
repo: "https://github.com/datacurve-ai/pier"
repo_commit: "07815d711ff90481c207f6c0eaeebfebf3cd7b60"
tags:
  - competitive-analysis
  - agent-eval
  - benchmark
  - architecture
  - pier
---

# Pier vs Unicorn (micro-eval) 对比分析

**日期**: 2026-06-02
**状态**: 分析完成
**对比仓库**: [datacurve-ai/pier](https://github.com/datacurve-ai/pier)
**分析版本**: `07815d711ff90481c207f6c0eaeebfebf3cd7b60`
**方法**: 读取 Pier README、Python package、模型层、job/trial runner、network allowlist、ATIF trajectory、viewer 与 tests；对照本项目 `2026-06-02-unicorn-design.md` 与 `mvp.local_pairwise.v1`。

---

## 1. 项目概述

### Pier

Pier 是一个 Harbor-compatible coding-agent benchmark runner。它读取 Harbor 任务格式，在 sandboxed environments 中运行 coding agent trial，并保留完整轨迹用于分析。

Pier 在 Harbor 基础上强调几件事：

- air-gapped task 下仍能安装和运行 CLI agent，通过 agent install spec 与 network allowlist 控制必要联网。
- 支持 `docker`、`modal` 等环境。
- 支持 `claude-code`、`codex`、`cursor-cli`、`gemini-cli`、`opencode`、`mini-swe-agent` 等 installed agents。
- 输出 augmented ATIF v1.7 trajectory。
- 提供 `pier view` 浏览 job、trial、trajectory。
- 提供 `pier critique run`，用新 agent 在新 sandbox 中检查已完成 trial。

**定位**: 标准 benchmark harness，偏 coding-agent 大规模/半可信任务执行与复盘。

**核心流程**:

```text
Harbor task directory -> JobConfig -> TrialConfig[]
  -> sandbox environment -> agent execution -> verifier
  -> trial artifacts / trajectory / rewards
  -> job stats / pass@k / viewer / critique
```

### Unicorn (micro-eval)

Unicorn 是 micro-eval 的模块化目标架构，服务 1-20 人 AI 小团队的 Agent / Skill 评测决策闭环。它不把自己定位为大模型 benchmark 平台，而是帮助团队在同一起点、同一任务集、同一评判边界下判断一次 agent / skill / prompt 改动是变好、变差、混合还是样本不足。

**定位**: 小团队本地评测工作台，核心是对比、复盘、成本和可行动结论。

**核心流程**:

```text
Task Authoring -> Evaluation Contract -> Command Adapter -> Same-start
  -> Run (Tasks x Configurations x Repetitions)
  -> Evidence Chain -> Basic Honest Stats -> Decision Report
```

---

## 2. 架构对比矩阵

| 维度 | Pier | Unicorn (micro-eval) | 判断 |
|------|------|----------------------|------|
| **定位** | Harbor-compatible benchmark runner | 小团队 agent/skill 决策工具 | 互补 |
| **任务格式** | 目录包：`instruction.md`、`task.toml`、`environment/`、`tests/`、`solution/`、`steps/` | 当前 legacy YAML；Unicorn 设计中有 TaskSpec / FixtureRef / RubricSpec | Pier 的任务包值得借鉴 |
| **执行单元** | Job -> Trial；每个 trial 有独立目录与结果 | Run -> RunCell；设计上有矩阵 cell，但当前实现仍是 flat `RunResult` | Pier 的落盘结构更成熟 |
| **可复现性** | `lock.json` 记录 replay 相关输入、task digest、agent/env/verifier config | Unicorn 有 SameStartSnapshot / Snapshot Gate；当前实现较弱 | Pier 的 lock 机制可直接借鉴 |
| **Sandbox** | docker / modal，支持网络限制与资源配置 | MVP 选择 git worktree + snapshot；远期支持 sandbox/remote | Pier 适合作为 Phase 3 参考 |
| **Agent 适配** | 内置多种 installed agent，知道各 CLI 的安装、配置、轨迹转换 | 黑盒 command adapter，不绑定具体 agent runtime | micro-eval 应保持黑盒，但可借鉴 adapter template |
| **网络策略** | agent 声明 network allowlist，环境执行 allowlist | Unicorn 有 sandbox/security 原则，但字段可更明确 | Pier 做法值得纳入 Agent/Environment 契约 |
| **评分/验证** | verifier 生成 reward，支持 reward stats 与 pass@k | Evaluation Layer = validation / grading / annotation / aggregation | 语义不同，但 pass@k 计算可借鉴 |
| **轨迹** | ATIF v1.7，一步一 turn，含 tool call、observation、metrics、subagent trajectory | Artifact/Trace Layer 抽象 TraceRef / EvidenceItem | ATIF 可作为 trace provider/import format |
| **复盘** | Viewer + critique job，能从 job 下钻到 trial/trajectory/verifier/critique | Decision Layer 要求 evidence-linked matrix summary | Pier 的 critique 可作为 Phase 2 evidence 扩展 |
| **UI** | 专注 job/trial/trajectory browser、效率图、heatmap、critique | 当前 UI 是 run viewer；目标是 decision surface | Pier viewer 的信息架构值得参考 |
| **上手复杂度** | 强 benchmark/sandbox 语义，依赖更多基础设施 | 目标是 10 分钟本地启动 | 不能照搬 Pier 全套 |

---

## 3. Pier 的关键设计点

### 3.1 Task Package 优于单条 prompt

Pier 的 `Task` 不是一条 prompt，而是一个可校验目录：

```text
task/
├── instruction.md
├── task.toml
├── environment/
├── tests/
├── solution/
└── steps/
```

这个结构把 coding-agent benchmark 的几个输入分开了：

- `instruction.md` 是 agent 看到的任务说明。
- `task.toml` 是任务元数据、环境、verifier、资源配置。
- `environment/` 是可复现执行环境。
- `tests/` 是 deterministic verifier。
- `solution/` 支持 oracle agent 或参考解。
- `steps/` 支持多阶段任务。

对 micro-eval 的启发：当前 legacy `Task.input_payload` 适合 hello-world 或摘要任务，但对 coding agent 不够。Unicorn 的 Asset Layer 应支持两种 profile：

1. `legacy_yaml_task`：继续服务 MVP 上手。
2. `task_package`：服务 coding agent / benchmark / fixture / verifier 场景。

这不需要推翻 Unicorn，反而是 TaskSpec 的自然展开。

### 3.2 Lock File 是可复现 run 的核心证据

Pier 的 `JobLock` 记录：

- Pier 版本与 git commit。
- sanitized CLI invocation。
- 并发、retry 策略。
- 每个 trial 的 task digest。
- agent config、environment config、verifier config。
- timeout multipliers。

并且它定义 canonical payload，排除 `created_at`、工具自身版本、invocation 这类非 replay identity 字段，用于比较 job 是否可 resume。

对 micro-eval 的启发：Unicorn 已经有 SameStartSnapshot、RunPlan、AssetSnapshot 和 Snapshot Gate，但当前实现只在 `Run.environment` 里记录很少字段。MVP 应尽早引入：

```text
.micro-eval/runs/{run_id}/lock.json
.micro-eval/runs/{run_id}/manifest.json
```

其中 `lock.json` 记录 replay-affecting input，`manifest.json` 记录 run 输出索引与 evidence/artifact 引用。这样 Decision Layer 的 `not_comparable` / `inconclusive` 才有硬依据。

### 3.3 Trial 目录结构可映射为 RunCell 目录

Pier 每个 trial 有固定输出目录：

```text
trial_dir/
├── agent/
├── verifier/
├── artifacts/
├── config.json
├── result.json
└── trial.log
```

多 step trial 还会把每个 step 的 agent / verifier / artifacts relocation 到 `steps/{step_name}/`。

micro-eval 可以直接映射为：

```text
.micro-eval/runs/{run_id}/
├── lock.json
├── manifest.json
├── decision.json
└── cells/
    └── {run_cell_id}/
        ├── invocation.json
        ├── agent/
        │   ├── stdout.txt
        │   ├── stderr.txt
        │   └── trajectory.json
        ├── validation/
        │   ├── result.json
        │   ├── stdout.txt
        │   └── stderr.txt
        ├── artifacts/
        │   └── manifest.json
        └── result.json
```

这会补齐 Unicorn 的 Artifact / Trace Layer，并让 UI 不再依赖一个扁平 `run-*.json`。

### 3.4 Network Allowlist 应成为契约字段

Pier 解决了一个真实 benchmark 问题：任务本身 `allow_internet = false`，但 Claude Code、Codex、Gemini CLI 这类 agent 在 sandbox 内安装和推理需要联网。Pier 让 agent 声明 network allowlist，并从配置中的 base URL 自动提取域名。

典型逻辑包括：

- `NetworkAllowlist.domains` 只允许 exact domain 或 leading-dot suffix。
- 从 agent env / config 中提取 `base_url`、`api_base`、`baseURL` 等 URL。
- 为 Codex 默认允许 `api.openai.com`，为 Gemini 默认允许 Google API 域，等等。

对 Unicorn 的启发：Agent Adapter Layer 和 Environment Layer 应明确包含：

```yaml
agent:
  install:
    steps: []
  network_allowlist:
    domains:
      - api.openai.com
      - endpoint.respan.ai

environment:
  network_policy:
    mode: block_all_except_allowlist
```

MVP 不一定执行网络隔离，但必须记录这些字段并进入 evidence / snapshot。否则同起点比较会漏掉“agent A 能访问 provider X，agent B 不能”的关键差异。

### 3.5 ATIF v1.7 可作为 Trace Provider 输入格式

Pier 的 trajectory model 使用 ATIF v1.7。关键字段包括：

- `schema_version`
- `session_id`
- `trajectory_id`
- `agent`
- `steps`
- `final_metrics`
- `continued_trajectory_ref`
- `subagent_trajectories`

其中 `Step` 明确区分：

- `source`: `system | user | agent`
- `message`
- `reasoning_content`
- `tool_calls`
- `observation`
- `metrics`
- `llm_call_count`

Pier viewer 的设计原则是：一个 ATIF step 对应一个 ViewStep，不制造 synthetic step，并保留原始 ATIF 对象。

对 micro-eval 的启发：不要把 ATIF 变成唯一 trace schema，但可以作为第一批 trace import/provider 格式：

```yaml
trace:
  providers:
    - type: atif_file
      path: "{cell_dir}/agent/trajectory.json"
```

这样 Codex、Claude Code、Cursor CLI 等 agent 的轨迹可以先以文件形式进入 Artifact/Trace Layer，再逐步接 Langfuse / LangSmith。

### 3.6 Critique Job 是解释性证据，不是评分替代品

Pier 的 critique job 不重新解决任务，也不替代 verifier reward。它把已完成 trial 的任务和结果 artifact 上传到新 sandbox，让 critique agent 检查：

- solving agent 是否误解任务、超时、API 失败、实现错误。
- task prompt、repo setup、hidden test、verifier 是否公平。
- environment 是否阻塞了公平评测。

这与 Unicorn 的 Evidence Model 高度一致：critique 不是最终 verdict，而是 `EvidenceItem(type=judge_rationale | human_annotation | task_quality_assessment)` 的一种来源。

建议 micro-eval Phase 2 引入：

```text
micro-eval critique <run_id> --agent <critic-config>
```

输出进入 `.micro-eval/runs/{run_id}/critiques/{critique_id}/`，Decision Layer 可以引用，但不能让 critique 覆盖 deterministic validation。

### 3.7 pass@k 的实现条件很清晰

Pier 只在 reward 是单一 0/1 指标时计算 pass@k。如果 rewards 缺失、多指标、非数值或非 0/1，则不计算。

这个边界值得 micro-eval 采纳。Unicorn 文档中已经提到 repetitions > 1 时 pass@k/pass^k 应升级为默认指标，但应补充限制条件：

- 只对 binary pass/fail 或单一 0/1 reward 默认计算 pass@k。
- 对多维 rubric score，不默认计算 pass@k，除非 EvaluationContract 明确指定二值化规则。
- 缺失 result 应按失败计入，或由 contract 明确指定 denominator policy。

---

## 4. 映射到 Unicorn 模块

| Pier 设计 | Unicorn 模块 | 建议 |
|-----------|--------------|------|
| Task directory package | Asset Layer | 增加 `TaskPackage` profile，兼容 legacy YAML |
| task checksum / content digest | Asset Layer / Stable IDs | 用于 `task_revision_id` |
| JobConfig -> TrialConfig[] | Configuration Layer | 对应 RunPlan 展开 |
| lock.json | Configuration + Environment + Artifact | MVP 必须引入 replay lock |
| TrialQueue + retry | Execution Kernel | 借鉴 retry/resume 语义 |
| Trial directory | Artifact/Trace Layer | 映射为 RunCell artifact directory |
| Agent install spec | Agent Adapter Layer | 作为 future adapter template，不绑定核心 |
| NetworkAllowlist | Agent Adapter + Environment | 纳入 config/snapshot/evidence |
| Verifier reward | Evaluation Layer | 对应 deterministic validation / reward evidence |
| ATIF trajectory | Artifact/Trace Layer | 支持为 trace import/provider |
| JobStats / pass@k | Evaluation + Decision | 加入 Basic Honest Stats |
| Viewer heatmap / trajectory browser | Decision Layer / UI | 参考信息架构，不照搬视觉设计 |
| Critique run | Evaluation + Artifact + Decision | Phase 2 作为解释性 evidence |

---

## 5. 对 micro-eval 的建议

### 5.1 立刻纳入 MVP 的设计

**1. Run lock / manifest**

优先级最高。它直接支撑 Unicorn 的 SameStartSnapshot、Snapshot Gate、Evidence Chain。

最小实现：

```text
.micro-eval/runs/{run_id}/lock.json
```

记录：

- schema version。
- micro-eval version / git commit。
- sanitized invocation。
- config hash。
- task ids + task revision digest。
- configuration ids + canonical digest。
- environment snapshot subset。
- max concurrency / retry / timeout。

**2. RunCell 目录结构**

把 flat `Run.results[]` 迁移为 manifest 索引 + cell directories。legacy JSON 可以继续导出，但不要作为唯一事实源。

**3. Task package 作为可选格式**

不废弃 YAML。新增 `tasks/<id>/instruction.md` + `task.yaml` 或 `task.toml` 解析器。MVP 可以先只支持：

```text
instruction.md
task.yaml
tests/test.sh
```

**4. deterministic subset**

借鉴 Pier 的 `n_tasks` + `sample_seed`：

```yaml
tasks:
  path: tasks/
  n_tasks: 10
  sample_seed: 0
  include: ["smoke-*"]
  exclude: ["slow-*"]
```

这对 benchmark 复现和快速 smoke run 很有用。

### 5.2 Phase 2 引入

**1. ATIF file provider**

让 agent 可以把 `trajectory.json` 写到约定位置，micro-eval 只负责收集和索引。

**2. critique run**

把“复盘失败原因”和“任务是否公平”建模为证据，不把它混进主评分。

**3. viewer 下钻能力**

当前 UI 只展示 run 表格。应借鉴 Pier 的下钻路径：

```text
Run -> Configuration/Task heatmap -> Cell -> Artifact -> Trajectory -> Validation -> Critique
```

### 5.3 Phase 3 或更晚

**1. Docker/Modal/Daytona 级 sandbox**

Pier 在这方面已经深入，但 micro-eval 的 MVP 不应立即承担这部分复杂度。

**2. installed agent registry**

Pier 内置多个 agent adapter。micro-eval 应保持黑盒 command adapter 为核心，只提供 template / preset，而不是把 Claude Code、Codex、Cursor CLI 的细节写入核心模型。

---

## 6. 不建议照搬的部分

### 6.1 不把 Harbor 格式作为唯一任务格式

Pier 是 Harbor-compatible，这是它的核心定位。micro-eval 的目标是 10 分钟本地上手，单 YAML/Markdown 任务仍然有价值。

更合适的策略是：

```text
legacy_yaml_task -> simple local eval
task_package -> coding agent / benchmark eval
harbor_import -> optional compatibility
```

### 6.2 不把 verifier reward 替代 DecisionReport

Pier 的 verifier reward 适合 benchmark 排名。micro-eval 的产品目标是决策闭环，需要保留：

- business impact tier。
- evidence citation。
- cost/time caveats。
- snapshot gate。
- `improved | regressed | mixed | inconclusive | not_comparable`。

reward 是证据，不是产品结论。

### 6.3 不过早引入完整 sandbox 基建

Pier 的 docker/modal 方案强，但成本也高。Unicorn 的 MVP Profile 选择 git worktree + snapshot 是合理的。现在应先把 snapshot / lock / artifact layout 做扎实。

### 6.4 不把 agent-specific adapter 做进核心

Pier 需要 installed agent adapter，因为它是 benchmark runner。micro-eval 应保持：

```text
Agent is a black box behind adapters
```

核心只依赖 `AgentInvocation` 契约。Codex/Claude/Cursor adapter 可以作为 preset 或插件。

---

## 7. 结论

Pier 验证了 Unicorn 的几个核心判断：

- 环境是输入的一部分。
- 结果必须落到可追溯 artifact，而不是只存摘要。
- 轨迹和成本是 agent 评测的核心证据。
- 可复现 run 需要 lock/manifest，而不是只靠最终结果 JSON。
- critique/复盘应作为证据层，而不是替代 deterministic validation。

Pier 最值得 micro-eval 借鉴的不是“做一个更大的 benchmark 平台”，而是这些工程契约：

1. `TaskPackage`
2. `Run lock`
3. `RunCell artifact directory`
4. `NetworkAllowlist`
5. `ATIF trajectory import`
6. `Critique as evidence`
7. `pass@k with strict applicability`

建议优先级：

| 优先级 | 借鉴项 | 原因 |
|--------|--------|------|
| P0 | Run lock / manifest | 直接支撑 same-start 和可复现结论 |
| P0 | RunCell artifact directory | 直接支撑 evidence chain 和 UI 下钻 |
| P1 | Task package | 让 coding-agent 任务从 prose 走向可验证 |
| P1 | deterministic subset / sample_seed | 让 benchmark 子集可复现 |
| P2 | ATIF file provider | 低侵入获得真实 trajectory |
| P2 | critique run | 增强失败复盘与 task fairness 分析 |
| P3 | network allowlist enforcement | 等 sandbox profile 成熟后启用 |

总体判断：Pier 与 micro-eval 定位不同，但 Pier 的 benchmark harness 经验正好补齐 Unicorn MVP 中最薄的工程落点。micro-eval 应把 Pier 当作”coding-agent benchmark 参考实现”，吸收其可复现、artifact、trace、critique 设计，而不是把自身改造成 Harbor clone。

---

## 8. 采纳追踪（2026-06-02 文档评审后）

基于本分析，经独立 code-reviewer 审查后，以下为各建议项的最终采纳状态。
审查依据：Unicorn Invariant #1（MVP is a Profile, not a fork）、#10（Profile capability must be explicit）、#11（Future capabilities attach to modules），以及”10 分钟上手”产品约束。

### 8.1 已采纳（写入设计文档）

| 建议项 | 采纳方式 | 写入位置 | 原因 |
|--------|----------|----------|------|
| Run lock / manifest | 以 `replay_canonical` 子对象嵌入 run.json（不新建独立 lock.json） | MVP Profile §6, Unicorn §10 M2 | 避免与 run.json 职责重叠；run.json 已是单一事实源，子对象保持此不变量 |
| RunCell artifact directory | 确认 MVP Profile §6 已有的 cells/ 结构正确 | MVP Profile §6（无代码改动） | Pier trial 目录验证了此方向，结构已存在 |
| pass@k strict applicability | 补充 binary-only、denominator policy、low confidence caveat | Unicorn §5.7（权威定义），MVP Profile §4.7（引用） | 规则只写一处避免双写；MVP 结构已支撑计算 |
| Task package（L2） | 写入 Unicorn §5.1 Asset Layer Future levels | Unicorn §5.1 | 属 L2 maturity 升级，不在 MVP 引入 |
| Deterministic subset（L2） | 写入 Unicorn §5.1 Asset Layer Future levels | Unicorn §5.1 | 属 L2，MVP 用 include/exclude glob 已足够 |
| ATIF file provider（L2） | 写入 Unicorn §5.6 Artifact/Trace Future levels（”file-based trace import”，不绑定版本号） | Unicorn §5.6 | Part I 契约不应绑定外部格式的具体版本 |
| Network allowlist（L2+） | 写入 Unicorn §5.4 Agent Adapter + §5.5 Environment Future levels | Unicorn §5.4, §5.5 | MVP 无网络隔离基础设施，记录但不强制会误导用户 |
| Critique run（L2） | 写入 MVP Profile §9（明确不含）+ §11（Phase 2 升级路径） | MVP Profile §9, §11 | 属 Evaluation+Decision Layer L2，Phase 2 引入 |
| Pier 参考来源 | 新增附录 A.9 | Unicorn 附录 A.9 | 记录竞品分析的学术诚信与可追溯性 |

### 8.2 未采纳 / 修改后采纳

| 原始建议 | 决定 | 原因 |
|----------|------|------|
| **独立 lock.json 文件** | 改为 run.json 内嵌 `replay_canonical` 子对象 | run.json 已含 RunPlan + SameStartSnapshot，新建 lock.json 会产生职责重叠（两个文件记录相同信息的不同子集），Decision Layer 不知以谁为准。子对象方案保持单一事实源。 |
| **Task package 写入 MVP Profile** | 仅写入 Unicorn §5.1 L2 Future levels，从 MVP 完全移除 | MVP 首要约束是”10 分钟上手”。引入目录包格式 + 目录 checksum + 解析器，对只有 3–5 个手写 YAML 任务的 MVP 用户毫无价值，增加认知负荷。且与 CLAUDE.md “MVP 不做：大规模任务库”直接冲突。本分析自身标为 P1（非 MVP）。 |
| **n_tasks / sample_seed 写入 MVP Profile** | 仅写入 Unicorn Future levels，从 MVP 完全移除 | 同上：MVP 场景是 3–5 个手写任务，不需要抽样逻辑。include/exclude glob 已覆盖子集选择需求。 |
| **Network allowlist 写入 MVP Profile（”记录但不强制”）** | 仅写入 Unicorn §5.4/§5.5 L2 字段，不在 MVP 引入 | MVP 使用 git worktree（Level 0 隔离），完全没有网络控制能力。用户看到配置项却得不到任何保障，制造虚假安全感。违背 Invariant #10（声明能力必须绑定可生效的 Profile）。本分析自身标为 P3。 |
| **ATIF v1.7 写入 Unicorn Part I 契约** | 改为”file-based trace import”写入 §5.6 Future levels，不指定 ATIF 版本号 | ATIF 是 Pier 的增强格式，非行业标准。Part I 契约中绑定外部格式版本号层级过高。Part II TraceProvider 章节可在实施时详述具体格式支持。 |
| **ATIF 作为 MVP Profile “future format” 声明** | 移除 | 在 MVP Profile 里写”future”条目违背 Invariant #10（Profile capability must be explicit —— 文档不能写”支持 X”而不说明在哪个 Profile 生效）。future 能力应存在于 Unicorn Design 的 L2 描述里，而非 Profile 文档中。 |
| **task_revision_id 含目录 checksum** | 推迟至 task package 实施时再定义 | 单 YAML task 用文件 hash、task package 用目录 checksum —— 同一 ID 字段两种生成规则违背 Invariant #9（稳定 ID 规则必须确定性）。等 task package 落地时引入 `task_package_digest` 独立字段，不改现有 ID 规则。 |
| **RunCell 目录重组（stdout 移入 agent/ 子目录）** | 不改动 | MVP Profile §6 的 cells/ 平铺结构（stdout.txt/stderr.txt 直接在 cell 目录下）已能工作。如果引入 agent/ 子目录，所有 ArtifactRef 的 `{cell_id}::{kind}::{hash}` → path 映射都要更新——但提案只改了目录没改 ID 规范，属于不完整变更。保持当前结构，Phase 2 如有需要再统一重组。 |

### 8.3 设计原则总结

本轮审查揭示的核心教训：

1. **分析文档的优先级标注必须在翻译为文档变更时被严格执行。** 本分析正确标注了 P1/P2/P3，但初次翻译时多项 P1+ 能力以”预留字段”名义绕过了 Profile 约束。Invariant #10 正是为阻止这种蔓延而存在。
2. **”预留字段”不是免费的。** 每个字段都是用户界面的一部分——即使标为 optional，也增加认知负荷和 schema 维护成本。只有当字段在当前 Profile 有执行效果时才写入 MVP。
3. **单一事实源优于多文件互相引用。** lock.json vs run.json 的矛盾证明：同一信息分布在两个文件时，消费方无法确定权威来源。嵌入子对象保持了 run.json 作为唯一事实源的地位。
