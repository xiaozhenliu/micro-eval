---
title: MVP 完成度与 Unicorn 就绪度评审 — 待办整改清单
doc_type: analysis
status: active
created_at: 2026-06-03T20:00+08:00
updated_at: 2026-06-03T20:00+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - review
  - tech-debt
  - mvp
  - todo
related:
  - docs/superpowers/specs/2026-06-02-mvp-profile.md
  - docs/superpowers/specs/2026-06-02-unicorn-design.md
  - docs/engineering/security-development-guidelines.md
  - docs/engineering/architecture-guardrails.md
  - docs/engineering/implementation-principles.md
---

# MVP 完成度与 Unicorn 就绪度评审 — 待办整改清单

## 1. 本文档是什么

这是一次**独立代码评审**的整改清单。评审问题是：当前代码是否完整完成了 MVP 阶段任务（对照 `docs/superpowers/specs/2026-06-02-mvp-profile.md`），并且能否进入 Unicorn 完整实现（`docs/superpowers/specs/2026-06-02-unicorn-design.md`）的下一轮规划。评审从四个方向展开：需求满足、安全、代码质量、工程规范符合度。

评审方法：每个方向由独立审查者只对照**真实源码**核验（不采信开发日志或 release-evidence 文档），每一条被标记为「阻断 / 重大」的发现，再由一个独立审查者**打开被引用的源码文件反向求证**，未通过求证的发现被降级或标为误报。本清单只收录通过求证后仍然成立的项。

## 2. 评审结论摘要

- **MVP 基本完成**，**可以**进入 Unicorn 下一轮规划。
- 经过反向求证后，**没有任何一条阻断级（blocking）发现存活**。所有初判为阻断/重大的项，在审查者打开真实文件核对后都被降级为「重大-漂移风险」「次要」或被判为误报。
- 安全（项目硬性合并门槛）通过：全库零 shell 注入向量、secrets 在持久化前完成脱敏、路径穿越在存储层与 UI 层均有 realpath 双重校验。
- 决定「MVP 是否完成」的两条核心不变量——同起点快照（Invariant #4）与证据链（Invariant #5）——在主路径上端到端打通。

四个方向裁决：

| 方向 | 裁决 | 覆盖度 |
| --- | --- | --- |
| 需求满足 | 通过（带保留） | 约 75% |
| 安全 | 通过 | 约 85% |
| 代码质量 | 通过（带保留） | 约 72% |
| 工程规范符合度 | 通过（带保留） | 约 80% |

下面的待办项是「带保留」中的具体内容，建议作为已追踪的技术债，折叠进 Phase 2 规划，而不是阻塞它。

## 3. 文件路径说明

本清单中的路径均为相对项目根目录（`/Users/xz/Projects/micro-eval/`）的路径。Python 源码在 `src/micro_eval/` 下，Web UI 源码在 `ui/src/` 下，测试在 `tests/` 下。行号为评审时点的近似位置，改动文件后可能漂移，请以函数/符号名为准定位。

---

## 4. 待办清单（按优先级）

### P1 — 唯一在反向求证后仍维持「重大」的项

#### TODO-1：消除 Web UI 重复实现的决策（verdict）算法，让 Python 成为唯一事实源

- **严重度（求证后）**：重大（层边界违规 + 跨语言漂移风险）。
- **涉及文件**：
  - `ui/src/lib/evaluation.ts`（第 93–145 行附近，函数 `recomputeDecision`）—— Web UI 的数据访问层，目前**整段重新实现**了决策算法。
  - `src/micro_eval/decision/summary.py`（第 12–74 行，函数 `build_decision`）—— Python 端 Decision 层的权威决策算法。
  - `ui/src/app/api/runs/[id]/cells/[cellId]/evaluate/route.ts`（第 35–38 行）—— 人工评分提交接口；它调用 `buildHumanEvaluation → appendEvaluationToRun → recomputeDecision → saveRun`，因此**当用户在 UI 提交人工评分时，是 TypeScript 这一侧在写入 run.json 里的权威 `decision` 字段**。
- **问题详述**：`recomputeDecision` 与 Python 的 `build_decision` 当前是逐行对应的复制：相同的 pass-rate 聚合、相同的 caveat 文案（例如 `low sample size for ${id}: repetitions < 3`、`single configuration run cannot produce comparative verdict`）、相同的 verdict 优先级阶梯（默认 inconclusive → 快照不一致时 not_comparable → 缺少 evaluation/evidence 引用时 needs_human_review）。两者现在结果一致，但任何一侧改动都必须手工同步另一侧，且没有任何测试校验跨语言等价。一旦漂移，「CLI 最后写入」和「UI 最后写入」会对同一个 run 产生不一致的结论。
- **为什么是最高优先级**：`CLAUDE.md` 把 Decision 层列为「产品核心」，架构守则（`docs/engineering/architecture-guardrails.md`）明确「UI 属于 Decision Layer 的展示，不直接产出结论」。这是唯一一条违反单一事实源原则的项，且越往后两侧越容易漂移。趁两端算法仍然一致时收口，成本最低。
- **建议动作**：让 Python 的 `build_decision` 成为唯一决策算法。UI 的 evaluate 接口在追加人工评分后，应改为**调用后端重新计算并由 RunStore 写回 `decision`**，或由前端消费后端已算好的 `decision`，删除 `recomputeDecision`。
- **规格依据**：`docs/engineering/architecture-guardrails.md`「依赖方向：UI 属于 Decision Layer 的展示」；`docs/engineering/implementation-principles.md`「Boundary First / Schema First」；`mvp-profile.md` §4.9 Decision Layer。

---

### P2 — 经求证成立的「重大」规格缺口

#### TODO-2：实现 §5 规定的「configuration 内容变了但 id 没变」可比性告警

- **严重度（求证后）**：重大（缺失一条强制 must 要求，削弱 P4 可比性信任）。
- **涉及文件**：
  - `src/micro_eval/config/planner.py`（第 46–94 行附近）—— 构建 RunPlan 的地方，这里**已经计算**了 `configuration_digests`（每个配置内容的哈希），并写入 `ReplayCanonical` 与 `SameStartSnapshot`。
  - `src/micro_eval/models/configuration.py`（第 98–109 行，`ConfigurationSpec.digest` 属性）—— 配置内容哈希（covers agent + skills_profile + parameters + repetitions）的来源。
  - `src/micro_eval/cli/run.py`（`run_command`，约第 22–97 行）—— run 启动主流程，目前是「加载 → 计划 → 执行 → 打印」，**没有读取历史 run 做对比**。
- **问题详述**：规格 `mvp-profile.md` §5 要求：run 启动时若发现某个 `configuration_id` 与历史 run 相同、但其内容哈希（config_content_hash）不同，必须发出告警 `configuration content changed but id unchanged — results may not be comparable with previous runs.`。当前代码只**写入**了 digest，从不**读回比较**：全库搜索 `content changed` / `config_content_hash` / `id unchanged` 均无结果。这意味着 Unicorn §4「display name 不能作为稳定 ID」的务实投影只实现了一半。
- **建议动作**：在 run 启动阶段，按 `configuration_id` 查找最近一次同 id 的历史 run（经 `src/micro_eval/store/run_store.py` 读取），比对 config_content_hash，不一致则向 stderr 输出上述告警（不阻塞执行）。
- **规格依据**：`mvp-profile.md` §5「configuration_id 稳定性说明」。

---

### P3 — 遗留死代码清理（删除前先补回归测试，见 P4）

#### TODO-3：删除生产路径已不可达的遗留执行/评分模块

- **严重度（求证后）**：次要（纯可维护性，零正确性/安全影响）。
- **涉及文件**：
  - `src/micro_eval/engine/runner.py`（类 `AgentRunner`，第 15、42 行起）—— 旧版执行器，仍带 baseline/candidate 二元模型与一套并行的 subprocess 实现，**生产 CLI 从不调用它**（`cli/run.py` 只用 `ExecutionKernel`），仅被 `tests/unit/test_runner.py`、`tests/e2e/test_full_flow.py` 引用而存活。
  - `src/micro_eval/engine/scorer.py`（类 `Scorer`，第 7、10 行起）—— 旧版评分器，docstring 谎称「wraps DeepEval」，实际只做 exact/contains 匹配（第 13–37 行）；同样仅被测试引用。
  - `src/micro_eval/models/schema.py` —— 旧版数据模型（二元 `Run`，含 `baseline_agent`/`candidate_agent` 字段；`RunResult` 含 `output_summary`）。**注意：此文件尚不能直接删**，见下条问题。
- **问题详述**：`runner.py` 与 `scorer.py` 是两套与 canonical 模型（`models/run.py` + `task.py` + `configuration.py`）并存的死代码，架构守则禁止 legacy baseline/candidate 模型继续作为新功能基础。但 `models/schema.py` 并非完全死代码——它仍被生产路径引用（见 TODO-4），所以删除要分步。
- **建议动作**：先完成 TODO-4（迁移 report 的 legacy 读取），再删除 `runner.py`、`scorer.py`，最后退役 `schema.py`。删除前务必先补上 TODO-5 的回归测试，避免连带删掉唯一覆盖「超时隔离」等契约的测试。
- **规格依据**：`docs/engineering/architecture-guardrails.md`「Run = Tasks × Configurations × Repetitions：baseline/candidate 只是 role」；`docs/engineering/implementation-principles.md`「Migration Is Explicit：不能继续扩大 legacy 模型」。

#### TODO-4：迁移 `cli/report.py` 对 legacy run.json 的读取，解除对 `schema.py` 的生产依赖

- **严重度（求证后）**：次要（这是 TODO-3 的前置条件）。
- **涉及文件**：
  - `src/micro_eval/cli/report.py`（第 15 行 `from micro_eval.models.schema import Run`；第 128 行 `legacy = Run(**raw)`）—— `report` 命令为了渲染旧格式 run.json，仍调用 legacy `Run` 模型。这一用法本身位于 loader/migration-bridge 位置，符合规范，但它是 `schema.py` 退役的最后一个生产依赖。
  - `src/micro_eval/config/loader.py`（第 21 行 `from micro_eval.models.schema import AgentConfig`；第 246–255 行 `legacy_agent_config`）—— 另一处 legacy 引用，但其调用方 `.baseline`/`.candidate` 兼容属性在生产路径已无任何调用者，可一并清理。
- **建议动作**：决定是否继续支持旧格式 run.json。若不再支持，移除 `_normalize_run_data` 的 legacy 分支与 `legacy_agent_config`；若仍需支持，将 legacy 读取逻辑迁出 `schema.py` 到一个明确命名的 migration 模块，再退役 `schema.py`。
- **规格依据**：`docs/engineering/implementation-principles.md`「Migration Is Explicit」。

---

### P4 — 补齐缺失的契约回归测试（删除遗留代码之前完成）

#### TODO-5：补齐 §10 要求的三条契约测试

- **严重度（求证后）**：次要（代码不变量当前成立，缺的是回归守卫）。
- **涉及文件**：
  - 目标新增测试位置：`tests/unit/`（当前缺少 `test_adapter.py` / `test_kernel.py`）。
  - 被测代码：`src/micro_eval/engine/kernel.py`（第 74 行，`adapter.invoke(...)` 委托）、`src/micro_eval/engine/adapter.py`（第 72 行 `asyncio.create_subprocess_exec`，第 91–101 行 timeout → terminate → kill 路径）。
- **问题详述**：`mvp-profile.md` §10 列了六条「Must not bypass」契约测试，目前有三条缺失或只覆盖了死代码：
  1. `test_kernel_uses_adapter`（Execution Kernel 必须经 AgentAdapter，不得直接起 subprocess）—— 无对应测试。
  2. `test_adapter_rejects_shell_string`（adapter 必须用 `create_subprocess_exec`、argv 列表、`shell=False`）—— 无对应测试；现有 `tests/unit/test_config_loader.py:80` 只在 YAML 加载层校验字符串命令被拒，未覆盖 adapter 调用层。
  3. 「单个 cell 超时不影响其他 cell」—— 仅 `tests/unit/test_runner.py:73`（`test_run_single_timeout`）针对**已死的** `AgentRunner` 测试，canonical 的 `ExecutionKernel → AgentAdapter` 超时与跨 cell 隔离零覆盖。
- **建议动作**：新增针对 canonical 路径的三条测试。务必在删除 `runner.py`（TODO-3）之前完成，否则「超时隔离」会变成完全无覆盖。
- **规格依据**：`mvp-profile.md` §10 契约测试 #1、#2 及关键测试用例「单个 cell 超时不影响其他 cell」。

#### TODO-6：为 zod 的 `EvaluationResultSchema` 补上 pass_fail → evidence_refs 的交叉校验

- **严重度（求证后）**：次要（潜在/防御性，当前 UI 写入路径不会触发）。
- **涉及文件**：
  - `ui/src/lib/schema.ts`（第 83–95 行，`EvaluationResultSchema`）—— 有 `pass_fail` 与 `evidence_refs` 字段，但**缺少** `.refine()` 强制「设了 pass_fail 就必须有非空 evidence_refs」。
  - `src/micro_eval/models/evaluation.py`（第 32–36 行，`pass_fail_requires_evidence` 校验器）—— Python 端**已强制**该不变量。
- **问题详述**：这是核心证据链契约的跨语言半边强制。当前 UI 写入路径（`buildHumanEvaluation` 总是写入非空 evidence id）不会产生违规数据，所以是潜在问题；但 zod 是 Python 契约的宽松超集，留着是隐患。
- **建议动作**：在 `EvaluationResultSchema` 上加 `.refine()`，与 Python 校验器对齐。
- **规格依据**：`mvp-profile.md` §4.7 与 §10 契约 #4。

---

### P5 — 规格符合性差异（与 Phase 2 一并补齐）

#### TODO-7：实现 CostMetric 成本模型与成本透传

- **严重度（求证后）**：重大（求证为真）／但非阻断（规格限定为 "if present"，trace 来源属 Phase 2）。
- **涉及文件**：
  - `src/micro_eval/models/run.py`（第 64 行 `AdapterResult`、第 83 行 `CellResult`）—— 两者目前都**没有** cost 字段。
  - `src/micro_eval/engine/kernel.py`、`src/micro_eval/engine/adapter.py` —— 从不构造 CostMetric（全库搜索 `CostMetric` 零命中）。
  - `src/micro_eval/models/decision.py`（第 32 行 `AggregationStats.cost_usd`）—— 字段存在但永远是 None。
  - `src/micro_eval/decision/summary.py`（第 27–33 行）—— 构造 `AggregationStats` 时不传 cost_usd。
  - `src/micro_eval/cli/report.py`（第 163、210 行）—— 已能用 `-` 优雅降级渲染空成本。
- **问题详述**：`mvp-profile.md` §4.6 定义了 `CostMetric`（currency / amount / source），§4.3 要求 `ExecutionResult.cost`，§4.9 把 "cost if present" 列为 Basic Honest Stat（标注「MVP 必须」）。这些目前完全未实现。非阻断的原因：规格本身限定 "if present"，MVP 阶段没有上报成本的 agent（trace 成本来源是 Phase 2 的 Langfuse），且下游 `cost_usd` 渲染已优雅降级为 `-`。
- **建议动作**：定义 `CostMetric` 模型，在 `AdapterResult` 增加 `cost` 字段，让 `build_decision` 把 cost 透传进 `AggregationStats.cost_usd`。与路线图上 Phase 2 的 Langfuse trace-cost 来源天然配对。
- **规格依据**：`mvp-profile.md` §4.3 / §4.6 / §4.9。

#### TODO-8：计算并记录 EvaluationResult 的 rubric_hash

- **严重度（求证后）**：次要（已被 task_revision_id 对 rubric 内容的哈希所缓解）。
- **涉及文件**：
  - `src/micro_eval/models/evaluation.py`（第 10–23 行 `EvaluationResult`）—— 没有 `rubric_hash` 字段。
  - `src/micro_eval/evaluation/validator.py`、`src/micro_eval/evaluation/human.py` —— 评分时从不计算 rubric 哈希。
  - `src/micro_eval/models/task.py`（第 64 行 `RubricSpec`）—— rubric 模型存在，但从未被哈希。
- **问题详述**：`mvp-profile.md` §4.7 要求 `rubric_hash`（对 task YAML 的 rubric 子树做 canonical JSON 序列化后取 sha256 hex[:16]）。该字段规格上是可空的，且 rubric 内容已被纳入 `task_revision_id`（`src/micro_eval/config/loader.py:242` 对整份 task YAML 文本哈希），所以可复现性未丢失，只是缺少细粒度溯源。
- **建议动作**：在生成 EvaluationResult 时计算 rubric 子树哈希并填入新字段，强化 P4 可复现/可比较定位。
- **规格依据**：`mvp-profile.md` §4.7「rubric_hash 规范」、§5 Stable IDs。

#### TODO-9：修正若干小的规格符合性差异

- **严重度（求证后）**：次要。
- 逐项（每项标明文件）：
  - **max_concurrency 默认值应为 4，当前为 2**。文件：`src/micro_eval/models/configuration.py`（第 116 行 `max_concurrency: int = 2`）、`src/micro_eval/cli/init.py`（第 42 行模板写 `max_concurrency: 2`）、`src/micro_eval/cli/run.py`（第 25 行 `--max-concurrency` 默认 None 回退到 2）。规格 `mvp-profile.md` §3 写「默认 4」。
  - **trace_id 格式与规格不一致**。文件：`src/micro_eval/engine/kernel.py`（第 78 行 `trace_id=cell.cell_id`）。规格 §4.4 要求 `f"{run_id}--{task_id}--{config_id}--rep{n}"`（双连字符、`rep{n}`），当前复用了以 `::` 分隔的 cell_id（`{run_id}::{task_id}::{config_id}::rep-{n}`）。信息相同、格式不同。
  - **output_truncated 计算了但未持久化**。文件：`src/micro_eval/engine/adapter.py`（第 124 行计算 truncated）、`src/micro_eval/models/run.py`（第 83–106 行 `CellResult` 无该字段）。截断标记没写进 report/UI 读取的 cell 结果。
  - **artifact 大小上限默认值与规格不符**。文件：`src/micro_eval/models/configuration.py`（第 118–119 行，output 与 artifact 上限都用 10MB）。规格 §4.4 要求 `max_artifact_size_bytes` 默认 50MB（与 `max_output_bytes` 10MB 区分）。
  - **adapter 的 error_class 分类命名与规格不同**。文件：`src/micro_eval/engine/adapter.py`（第 112 行起）。规格 §4.4 写 `error_class: Literal["success","timeout","crash","nonzero"]`，代码改用 `status`（CellStatus 枚举）+ 自由文本 `failure_mode`，且未把 "crash"（信号杀死）从 "nonzero" 中区分出来。属说明性伪代码与实现的命名差异，非能力缺失。
  - **canonical schema 字段超出权威规格但未先更新规格**。文件：`src/micro_eval/models/artifact.py`（第 10–37 行）。`ArtifactRef` 增加了 sha256/media_type/redacted/warning，`EvidenceItem` 增加了 artifact_refs/metadata，这些都是合理的前瞻字段且 zod 已镜像，但 `CLAUDE.md` 要求「先更新权威来源再更新实现」。应回写 `mvp-profile.md` §4.6 的数据模型，让规格与实现一致。
  - **SecretRedactor 命名与「Run 级单次构造」流程与规格不同**。文件：`src/micro_eval/engine/adapter.py`（第 19–29 行 `Redactor` 类）。规格 §4.8 命名为 `SecretRedactor` 且要求 run 启动时构造一次；实现命名为 `Redactor` 且每次 invoke 重建。功能等价、接线正确，仅命名与构造时机不同。
- **建议动作**：按规格修正默认值与 trace_id 格式；持久化 output_truncated；其余命名/字段差异，选择「改实现对齐规格」或「更新规格对齐实现」，二选一并保持权威来源同步。

---

### P6 — 安全加固（单用户本地威胁模型下非阻断）

> 说明：以下三项在「config 作者 = 可信本地用户、被评测 agent 才是不可信方」的 MVP 威胁模型下都不构成可利用漏洞，但属于真实的纵深防御缺口，建议追踪。

#### TODO-10：约束 git_repo 类型 workspace.path 不得逃出项目根

- **严重度（求证后）**：次要（纵深防御缺口）。
- **涉及文件**：`src/micro_eval/engine/workspace.py`（第 153–162 行，`_resolve_source_path`）—— 只校验路径存在且是 git 仓库，**不校验位置**。绝对路径（如 `/Users/victim/secret-repo`）或 `../` 都能通过，随后会对该仓库建 worktree 并收集 `git diff` 进入 evidence。
- **对照**：`src/micro_eval/store/run_store.py`（第 30–33 行）与 `src/micro_eval/store/artifact_store.py` 都有 `relative_to(project_root)` 守卫，唯独这里没有。
- **建议动作**：加 `relative_to` 守卫，或对越界 path 显式告警（caveat）。
- **规格依据**：`docs/engineering/security-development-guidelines.md`「Workspace and Artifact Handling — 路径穿越必须被拒绝」。

#### TODO-11：让 ArtifactStore 不要在自己没做脱敏时自报 redacted=true

- **严重度（求证后）**：次要（信任边界脆弱性）。
- **涉及文件**：`src/micro_eval/store/artifact_store.py`（第 70–82 行，`index_file`）—— 它根据 `is_binary` 直接给 ArtifactRef 设 `redacted = not is_binary`，**自身从不调用脱敏器**，正确性完全依赖上游 adapter 已写入脱敏后的字节。
- **问题详述**：canonical 路径下成立（adapter 已脱敏），但 manifest 对任何调用方都声称 redacted=true。未来若有新调用方索引未脱敏文件，会被误标为已脱敏，而 UI（`ui/src/lib/api.ts:98` 原样返回 text/plain）会把原始 secret 当作已脱敏内容返回。
- **建议动作**：让 redacted 标记反映实际经过的脱敏操作，或在 store 层补一道脱敏，避免「自报」与「实际」脱钩。
- **规格依据**：Unicorn Invariant #8「Secrets are never evidence」。

#### TODO-12：统一二进制检测阈值（adapter 扫全量，store 只扫前 1024 字节）

- **严重度（求证后）**：次要。
- **涉及文件**：`src/micro_eval/engine/adapter.py`（第 324 行 `_redact_text_file`，扫描整个保留缓冲区判断二进制）对比 `src/micro_eval/store/artifact_store.py`（第 70 行 `index_file`，`is_binary = b'\x00' in data[:1024]` 只扫前 1024 字节）。
- **问题详述**：一个前 1KB 是文本、NUL 字节出现在 offset > 1024 的文件，会被 store 判为 text/plain 且 redacted=true 并被 UI 原样返回。两侧阈值不一致导致 store 的 redacted/media_type 标签可能出错。
- **建议动作**：统一二进制检测策略（建议两侧都扫全量或采用同一阈值）。
- **规格依据**：`docs/engineering/security-development-guidelines.md`「binary 风险必须被拒绝、降级或显式记录 warning」。

---

### P7 — 功能正确性与健壮性

#### TODO-13：让 file_exists / command 类校验针对 agent 实际工作目录，而非 artifact 输出目录

- **严重度（求证后）**：次要（泄漏抽象，对 git_repo/files 类 workspace 影响实际可观测性）。
- **涉及文件**：
  - `src/micro_eval/evaluation/validator.py`（第 93–119 行）—— `file_exists` 用 `target = (cell_dir / rel).resolve()` 检查；`command` 类以 `cwd = cell_dir` 运行。
  - `src/micro_eval/engine/kernel.py`（第 69 行 `cell_dir = artifact_store.cell_dir(...)`、第 153 行把同一 `cell_dir` 传给 `validate_cell`）—— 这里的 `cell_dir` 是 `.micro-eval` 的 **artifact 目录**，不是 agent 实际执行、改文件的 **workspace（prepared.path）**。
- **问题详述**：因此一个 `file_exists` 期望检查的是 artifact 输出目录，而非 agent 真正执行的工作区。对 git_repo / files 类 workspace，期望无法观测到工作区内的实际改动。这是校验作用域与执行作用域之间的抽象泄漏。
- **建议动作**：明确每类 expectation 的作用域。对需要观测 workspace 改动的校验，传入 `prepared.path` 而非 artifact `cell_dir`；或在文档中明确 file_exists/command 只作用于 agent 声明的 output 目录。
- **规格依据**：`mvp-profile.md` §4.1 / §4.7 expectations。

#### TODO-14：扩大 Kernel 单 cell 异常捕获范围，保证部分完成而非整轮中止

- **严重度（求证后）**：次要。
- **涉及文件**：`src/micro_eval/engine/kernel.py`（第 81 行 `except (WorkspaceError, AdapterError)`；第 42–45 行 `for completed in asyncio.as_completed(tasks): result = await completed`）。
- **问题详述**：`_run_cell` 只捕获 `WorkspaceError` / `AdapterError`。invoke 之后的工作（快照门、artifact 写入、`validate_cell`、写 evaluation.json，约第 104–165 行）不在保护范围内。`kernel.run` 的 `await completed` 会把任何未预期异常重新抛出，导致整个 `run()` 中止、其他在途 cell 变成孤儿、run 记录未 finalize（无 partial 状态）。一个畸形 cell 可能丢掉所有兄弟 cell 的结果。
- **建议动作**：把单 cell 的后处理也纳入异常隔离，捕获更宽的异常并记为该 cell 失败，保证其余 cell 与 run 记录优雅完成（partial）。
- **规格依据**：`mvp-profile.md` §4.3「timeout / 隔离 / 结果收集（优雅部分完成）」。

---

### P8 — 文档/规范一致性

#### TODO-15：修正 CLAUDE.md 指向的安全检查清单路由

- **严重度（求证后）**：观察项。
- **涉及文件**：
  - `docs/engineering/security-guidelines.md` —— 现已重构成一个约 1.8K 的索引文件，**不再包含**「Code Review Checklist」（搜索 `Code Review Checklist` / `合并门槛` 均零命中）。
  - `CLAUDE.md` —— 硬规则仍要求「完成后必须逐条过 security-guidelines.md 末尾的『Code Review Checklist』」，但该清单已移入 `docs/engineering/security-development-guidelines.md`。
- **问题详述**：CLAUDE.md 的路由/合并门槛指令现在指向一个不再含清单的文件，削弱了「安全即合并门槛」这条规则的可执行性。
- **建议动作**：更新 `CLAUDE.md` 的安全检查清单路由，指向 `docs/engineering/security-development-guidelines.md`（清单实际所在）。
- **规格依据**：`CLAUDE.md`「Engineering guidelines routing」与「安全验收与功能验收同为合并门槛」。

---

## 5. 已驳回的发现（透明记录，无需处理）

下列项在初审被标为问题，但反向求证后判定**不成立或属规格内行为**，记录在此以免后续重复提出：

- **「Decision 层永远不会输出 improved/regressed/mixed」**——属规格明确许可的状态，非缺陷。`mvp-profile.md` §8 明确「P0-a 可独立交付一个『能跑但 verdict 全是 inconclusive』的版本」，比较型 verdict 是 P0-b/Phase 2 升级。三个枚举值是为后续阶段前置声明的 taxonomy，不是死代码。
- **「task_revision_id 未包含外部 rubric 文件内容」**——外部 rubric 文件引用本就不在 MVP 范围（§2 Profile 表 Asset Layer 限定「inline rubric」）。对 MVP 实际要求的「task YAML 整体 hash（含内联 rubric）」，`src/micro_eval/config/loader.py:242` 对整份文件文本哈希，已正确满足。
- **「legacy AgentRunner 路径脱敏更弱、缺 symlink/hardlink 加固」**——该路径是死代码，仅被测试引用，生产 CLI（`cli/run.py → ExecutionKernel → AgentAdapter`）从不经过它，无法在生产中触发。（清理动作并入 TODO-3。）
- **「legacy schema.py 被生产 CLI 路径引用，违反隔离」**——其引用位于 loader / migration-bridge 位置，正是 `implementation-principles.md`「Migration Is Explicit」允许的地方，未被扩张为新功能基础。（仍建议按 TODO-4 退役，但不构成违规。）

## 6. 下一步建议

整改不阻塞 Unicorn 下一轮规划。建议把本清单作为 Phase 2 计划的输入，按 P1 → P2 → P3/P4（绑定执行：先补测试再删代码）→ P5–P8 的顺序推进。其中 TODO-1（决策算法单一事实源）价值最高，建议优先排期。
