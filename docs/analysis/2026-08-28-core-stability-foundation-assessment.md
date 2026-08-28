---
title: micro-eval 正常 workspace 生命周期架构分析
doc_type: analysis
status: active
created_at: 2026-08-28T10:40+08:00
updated_at: 2026-08-28T14:31+08:00
owner: micro-eval maintainers
source_of_truth: false
tags:
  - workspace-lifecycle
  - architecture
  - specification-alignment
related:
  - micro-eval-prd.md
  - docs/superpowers/specs/2026-06-02-unicorn-design.md
  - docs/superpowers/specs/2026-06-02-mvp-profile.md
  - docs/engineering/architecture-guardrails.md
---

# micro-eval 正常 workspace 生命周期架构分析

## 1. 范围与结论

本文只分析本地 workspace 的正常生命周期：workspace 能成功建立，agent invocation
能返回 `AdapterResult`，validator 与可选 judge 能返回结果，持久化和 cleanup 能正常完成。
agent 退出码非零或 deterministic validation 不通过仍属于正常控制流，因为系统可以完整地
观察、评价并提交该 cell。

本文暂不把以下情况纳入修复范围：用户取消、timeout、进程或 runner crash、机器宕机、
prepare 半失败、持久化半失败、cleanup 失败、恢复、重试、remote session 失联。这些问题
保留在附录 A，不作为 issue 05 的实现前提。

结论如下：

1. 设计文档已经把本地 ephemeral workspace、终态 validation、diff、Artifact/Evidence 和
   cleanup 放入当前基础 Profile；这个问题不能被解释为“路线图尚未覆盖”。
2. 当前 codebase 的用户可见主行为是**错误实现**：单轮路径先 cleanup 再 validation，会
   稳定制造假失败；同时 diff 未接入属于**不完整实现**，单轮与会话路径不同属于
   **实现冲突**。
3. 当前 issue 05 已把本地 workspace 的正常生命周期固化为独立 P0，并将 wheel/UI 分发与
   异常生命周期排除。
4. 不需要增加第九个顶层 Module。Unicorn Design 的八个顶层 Module 足够；当前缺少的是
   Execution Kernel 内部的深 Module，以及 Environment、Artifact/Trace、RunStore 之间的
   三个显式 Seam。
5. 以更新后的 issue 05 作为任务契约、本文作为架构解释，现在可以可靠形成正常路径的
   修复方案；§8 逐项核对其完整性，§9 单独汇报仍需后续设计的缺口。

## 2. 根据设计意图确定 workspace 的语义与生命周期

长期架构以 [Unicorn Design](../superpowers/specs/2026-06-02-unicorn-design.md) Part I
为权威来源；当前最低能力以
[MVP Profile](../superpowers/specs/2026-06-02-mvp-profile.md) 为投影；
[Phase 2 PRD](../../micro-eval-prd.md) 只是 `0.2.0` 的非权威产品快照。

### 2.1 Workspace 的三个语义

Workspace 同时是：

1. **环境输入**：来源、commit、fixtures、setup、toolchain、isolation、trust 和 network
   policy 参与 same-start 与可复现性判断。
2. **受控执行上下文**：每个 RunCell 获得独立 workspace，agent 以它为 cwd；任务修改
   不应落到宿主项目根目录，也不应被其他 cell 共享。
3. **终态事实的临时载体**：agent 返回后的文件、代码修改和可运行状态由 Environment
   暂时持有，供 Artifact/Trace 取证和 Evaluation 读取。

Workspace 不是 run 的持久化报告目录。持久化对象位于 `.micro-eval/runs/{run_id}/`，
必须经过路径限制、容量限制和脱敏。默认 workspace 是 ephemeral：每个 cell 建立一次，
所有依赖其终态的读取完成后销毁。

| 对象 | 语义 | 生命周期 |
| --- | --- | --- |
| Workspace | agent 的可变执行环境与终态事实来源 | 随 cell 建立，在正常最终化后销毁 |
| SameStartSnapshot / CellSnapshot | 起点、provider 与 cleanup 事实 | 随 run 持久化 |
| Adapter output directory | stdout、stderr、显式输出与 conversation log | 随 run 持久化 |
| WorkspaceObservation | Environment 对终态的一次有界观察 | 只跨越最终化过程，不直接成为 canonical schema |
| Artifact / Evidence / Evaluation | 可引用、可复核的持久事实与评价 | 随 run 持久化并供 Decision 使用 |

### 2.2 正常生命周期的规范顺序

正确顺序不是简单地把 cleanup 往后挪，而是明确三个时点：agent process 返回、cell
最终化完成、canonical cell commit 完成。

```text
resolve WorkspaceSpec from RunPlan
→ Environment prepares an isolated workspace and runs setup
→ Environment records the prepared start and Execution evaluates the snapshot gate
→ Agent Adapter invokes the agent with workspace as cwd
→ Adapter returns a normal control-flow outcome
→ Environment observes the pre-validation terminal state
→ Artifact/Trace persists redacted and bounded adapter/workspace facts
→ Evaluation runs deterministic validators against the still-live workspace
→ Evaluation optionally runs supplemental judgment
→ Execution assembles a finalized cell value
→ Environment cleans the ephemeral workspace and supplies cleanup_status
→ RunStore commits evaluation.json, result.json, and the RunRecord projection
→ Decision consumes persisted Evaluation and Evidence after cells complete
```

必须保持以下不变量：

- snapshot gate 在 agent invocation 前求值；它描述起点，不描述 cleanup 后的目录状态。
- `WorkspaceObservation` 在 adapter 返回后立即产生，并早于 command validator。validator
  命令可能修改 workspace，这些修改不属于 validation 前的终态 diff，不能污染先前取证。
  该 diff 默认相对 source `HEAD`，不是对“纯 agent delta”的无条件声明。
- `file_exists` 与 command validator 在 workspace 存活时运行；只有显式使用
  `{output_dir}` 才切换到持久化 output directory。
- 所有必须读取 workspace 才能得到的事实，在 cleanup 前变成内存中的稳定模型或已落盘
  Artifact/Evidence。
- `CellResult` 在 cleanup outcome 已知后提交，因此正常完成的结果能准确记录
  `cleanup_status=cleaned`。
- cleanup 不是 Evaluation，不能改变 deterministic validation 或 judge 已得出的结论。

### 2.3 三类 workspace 的正常行为

| 类型 | 建立 | agent 返回后的观察 | 正常结束 |
| --- | --- | --- | --- |
| `blank` | 建立空目录并运行可选 setup | validator 读取终态；不默认归档整个目录 | 持久化 Adapter 输出与 validation evidence 后删除目录 |
| `files` | 复制声明 fixture 到独立目录并运行 setup | validator 读取对 fixture 的最终修改；不默认归档整个目录 | 与 `blank` 相同 |
| `git_repo` | 从解析后的 commit/ref 建立独立 worktree 并运行 setup | 先收集 tracked、staged 与安全的 untracked 文本修改，再运行 validator | diff、Evidence 与 Evaluation 可复核后移除 worktree |

`blank` 和 `files` 不具备天然 diff 语义。当前 Profile 不应偷偷把整个 workspace 复制为
Artifact；通用文件归档需要声明式选择策略，见 §9.2。agent 如果主动写入
`MICRO_EVAL_OUTPUT_DIR`，这些文件仍按现有 ArtifactStore 规则持久化。

## 3. 按当前八个顶层 Module 覆盖正常生命周期

### 3.1 职责映射

| 顶层 Module | 正常生命周期职责 | 不应承担的职责 |
| --- | --- | --- |
| Asset | 提供任务、fixture 与 rubric 等不可变输入 | 不创建或清理 workspace |
| Configuration | 把配置解析为含 WorkspaceSpec 的 RunPlan | 不执行 agent 或 validator |
| Execution Kernel | 调度 RunCell、限制并发、调用内部 `CellLifecycle`、提交 cell | 不实现 provider、Artifact 脱敏或评分规则 |
| Agent Adapter | 把 agent 运行转换为 AdapterResult 与模式特有事实 | 不判定 pass/fail，不执行 cleanup |
| Environment / Reproducibility | prepare、setup、起点 snapshot、终态观察、cleanup | 不创建 ArtifactRef，不决定 Evaluation |
| Artifact / Trace | 脱敏、有界持久化并产生 ArtifactRef、EvidenceItem、TraceRef | 不直接操作 workspace 生命周期 |
| Evaluation | 先 deterministic validation，再执行可选 supplemental judgment | 不删除 workspace，不直接形成 winner |
| Decision | 只读取持久化 Evaluation 与 Evidence 得出比较结论 | 不读取临时 workspace 或裸 stdout |

RunStore 是 Store Behind Interfaces 的持久化实现，不是第九个领域 Module。它负责把已经
形成的 canonical 对象写入稳定路径，Execution Kernel 不应自行拼接
`cells/{cell_id}/evaluation.json`。

### 3.2 Execution Kernel 内部的深 Module

当前 `_execute_cell()` 同时承担 prepare、两种 invocation、Artifact、Trace、snapshot、
validator、judge、JSON 写入、结果组装和 cleanup；会话路径又复制了一套 finalization。
这个 Implementation 很大，但没有对应的小 Interface，因此 ordering 规则分散且难以测试。

应在 `micro_eval.engine` 内引入内部 `CellLifecycle` Module。它仍属于 Execution Kernel，
不是新的顶层领域 Module。构造时绑定 plan/run context 和既有依赖，对调度器只暴露一个
Interface：

```python
@dataclass(frozen=True)
class FinalizedCell:
    result: CellResult
    evaluations: tuple[EvaluationResult, ...]

class CellLifecycle:
    async def execute(self, cell: RunCell) -> FinalizedCell: ...
```

这个 Module 具有足够的 Depth：一个很小的 Interface 隐藏一整条正常生命周期顺序。
它也有明确 Leverage：单轮与 conversational 两条真实路径共用同一 finalization，集成测试
只需穿过 `execute()` 这个测试面。其 Locality 是所有终态 ordering 规则集中在一个文件，
而不是散落在 Kernel、conversation helper 和测试 fixture 中。

Deletion test 也成立：如果删除这个 Module，prepare/observe/validate/persist/cleanup 的顺序
会重新复制到至少两条执行路径；它不是只转发调用的浅包装。

### 3.3 Agent invocation 的内部 Adapter Seam

单轮与 conversational 的执行细节不同，但它们必须向 `CellLifecycle` 交回共同事实：

```python
@dataclass
class InvocationOutcome:
    adapter_result: AdapterResult
    redactor: Redactor
    mode_artifacts: tuple[PendingArtifact, ...] = ()
    conversation_context: ConversationContext | None = None
```

单轮 Adapter 和 conversational Adapter 是两个真实实现，因此这是成立的 Seam，而不是为
假想未来提前抽象。conversation score 仍属于 Evaluation；Adapter 只返回 conversation
事实。两种 Adapter 返回后都进入同一个 `observe → persist → validate → cleanup` 尾段。

## 4. 必须补齐的 Interface

### 4.1 Environment：终态观察

现有 `WorkspaceProvider.collect_artifacts() -> list[ArtifactRef]` 把 Artifact Layer 拥有的
类型反向交给 Environment，是错误的所有权关系：provider 没有 run manifest、脱敏器和
ArtifactStore 路径，不能可靠地产生持久引用。

应以 Environment 拥有的原始观察替换正常路径上的 `collect_artifacts()` 与裸
`collect_diff()`：

```python
@dataclass(frozen=True)
class WorkspaceObservation:
    workspace_type: WorkspaceType
    diff_text: str | None = None
    diff_truncated: bool = False
    warnings: tuple[str, ...] = ()

class WorkspaceProvider(Protocol):
    def observe_final(
        self,
        handle: WorkspaceHandle,
        *,
        byte_limit: int,
    ) -> WorkspaceObservation: ...
```

`WorkspaceManager.observe_final(prepared, byte_limit=...)` 是 Execution 使用的 Environment
Interface；provider 选择与 handle 细节留在其 Implementation 内。所有 provider Adapter
需要满足形状，但本 issue 只要求 local logical/os-policy 路径有真实 diff 语义；remote
可以返回带 `observation_unavailable` warning 的空观察，不能借此宣称 remote 完整交付。

Unicorn Design Part II §3.4.4 当前仍写 `collect_artifacts() -> list[Artifact]` 与
`collect_diff()`，而 runtime Protocol 已进一步漂移为直接返回 ArtifactRef。实施 issue 05
时必须同步更新这段权威 Interface：Environment 输出原始 observation，Artifact/Trace
才产生持久引用。否则修完 codebase 后，设计来源会再次与实现冲突。

对于 `git_repo`，`diff_text` 的当前 Profile 语义必须固定为：

- 基于 source `HEAD`，包含 tracked 文件的 staged 与 unstaged 修改；
- 包含未被 `.gitignore` 排除的 untracked 普通文本文件；
- setup 若留下非 ignored 修改，这些变化也会出现在终态 diff，并产生
  `diff_includes_setup_changes` caveat；当前 Interface 不把它误称为纯 agent delta；
- symlink、hardlink、binary 或单文件/总量超限内容不读取正文，只留下 warning；
- 捕获阶段就执行总字节上限，不能先用无界 `capture_output=True` 把任意 diff 全部读入内存；
- provider 返回原始有界文本，Artifact/Trace 在写盘前统一脱敏；
- truncated/skipped 状态必须通过 ArtifactRef warning 和 Evidence caveat 可见。

### 4.2 Environment：setup 结果

`GitWorktreeProvider._run_setup()` 已返回退出码，但 `create()` 丢弃它，
`WorkspaceManager.prepare()` 又把 `CellSnapshot.setup_exit_code` 固定为 `None`。正常成功的
setup 应通过 `WorkspaceHandle.setup_exit_code: int | None` 传回并记录 `0`；没有 setup 时
保持 `None`。非零 setup 的失败策略属于异常路径，本 issue 不扩展状态机。

### 4.3 Artifact/Trace：持久化 workspace 观察

ArtifactStore 需要一个不暴露路径拼接的 Interface：

```python
def persist_workspace_observation(
    self,
    cell_id: str,
    observation: WorkspaceObservation,
    redactor: Redactor,
) -> tuple[ArtifactRef, ...]: ...
```

Implementation 负责：先脱敏，再执行 Artifact cap，原子写入 `workspace.diff`，更新
manifest，并把 Environment warning 映射到 ArtifactRef warning。`CellLifecycle` 再创建
引用这些 ArtifactRef 的 workspace EvidenceItem。Environment 不导入 ArtifactRef，
ArtifactStore 也不负责 cleanup。

### 4.4 RunStore：cell commit

Execution Kernel 当前直接写、再直接读 `evaluation.json`，绕过了 Store Interface。应增加：

```python
def commit_cell(
    self,
    record: RunRecord,
    finalized: FinalizedCell,
) -> RunRecord: ...
```

它一次写入 evaluation、result，并更新 `RunRecord.results` 与
`RunRecord.evaluations`。Artifact/Evidence 仍由 ArtifactStore manifest 管理；run 完成时
只做 manifest projection 和 Decision，不再扫描 cell 文件重建 evaluations。

在本文的正常路径范围内，这个 commit 不要求 crash-safe journal 或两阶段提交；那些属于
附录 A。不过 Store Interface 本身现在就应收敛，否则 Kernel 会继续知道持久化布局。

## 5. 正常场景的逐步行为

### 5.1 建立与准备

1. Configuration 已经把 Task、Configuration、repetition 与 guardrails 固化到 RunPlan。
2. WorkspaceManager 依据 isolation level 选择 WorkspaceProvider Adapter。
3. provider 在当前 eval project 的
   `.micro-eval/workspaces/{run_id}/{cell_id}/` 内建立 `blank`、`files` 或 `git_repo`。
4. provider 在 workspace 中以 argv-only 执行 setup，并把成功退出码传入 handle。
5. WorkspaceManager 记录 prepared snapshot；Execution 立即计算 snapshot gate。
6. gate 的 caveat 可以降低比较强度，但不能偷偷改用宿主目录继续执行。

### 5.2 Agent 运行

- Agent Adapter 的 cwd 是 prepared workspace；output directory 是独立的持久化 cell 目录。
- stdout、stderr、exit code、latency、显式 output、truncation 和 trace ID 进入
  AdapterResult。
- agent 返回时 workspace 保持原样，不触发 cleanup。
- agent 正常返回但退出码非零时，仍执行终态观察与 deterministic validation；结果可以是
  failed/error，但证据链必须完整。

### 5.3 终态观察与 Artifact

1. `CellLifecycle` 先调用 `WorkspaceManager.observe_final()`。
2. git worktree 的观察表示 validation 前终态相对 source `HEAD` 的变化；它可能包含
   setup 产生的非 ignored 修改，并必须附带 caveat。之后 validator 产生的修改不进入
   该 diff。
3. ArtifactStore 持久化 stdout、stderr、显式 outputs、conversation log 和可用 diff。
4. Process、snapshot 和 workspace Evidence 引用这些持久 Artifact；Evidence 不引用
   cleanup 后才会消失的绝对 workspace 路径作为唯一证据。

### 5.4 Evaluation

1. deterministic validator 在仍存在的 workspace 上运行。
2. `file_exists` 默认以 workspace 为根；`{output_dir}` 才切换范围。
3. command validator 继续使用 argv-only、受限 cwd 和 timeout；其 stdout/stderr 经过脱敏
   后进入 validation summary。
4. deterministic fail 不能被 supplemental LLM/conversation score 覆盖成强通过。
5. EvaluationResult 与 Evidence refs 在 cleanup 前已经形成稳定对象。

### 5.5 Cleanup、cell commit 与 Decision

1. `CellLifecycle` 在所有 workspace 读取结束后调用 Environment cleanup。
2. 正常 cleanup 把 CellSnapshot 更新为 `cleanup_status=cleaned`。
3. `CellLifecycle` 组装最终 CellResult 与 evaluations 并返回 FinalizedCell。
4. Execution Kernel 调用 `RunStore.commit_cell()`，随后才触发 `on_cell_complete`。
5. 所有 cell 完成后，Kernel 从 ArtifactStore manifest 与已提交 evaluations 形成 RunRecord
   projection；Decision 只消费这些持久对象。

## 6. 文档声明的当前与未来范围是否准确

本节只比较文档，不用 codebase 反推产品意图。

### 6.1 当前范围

Phase 2 PRD 与 MVP Profile 已经共同声明：

- 每个 cell 使用 project-local workspace；
- 支持 `blank`、`files`、`git_repo`；
- agent cwd 是所分配 workspace；
- 支持 `file_exists` 与 argv-only command validator；
- Artifact L1 包括 stdout、stderr、output files 和 diff；
- 持久化 snapshot、Artifact、Evidence、Evaluation，并在结束后 prune workspace。

因此，建立 workspace、终态观察、deterministic validation、diff 持久化和正常 cleanup
都是当前基础 Profile 中本地 workspace 能力的组成部分。

### 6.2 未来范围

未来范围包括 persistent/manual retain、snapshot/restore、checkpoint/resume、分布式运行、
完整 remote provider 生命周期、可配置 cleanup policy，以及异常恢复状态机。它们改变保留
策略或执行位置，但不改变“先观察和验证终态，再 cleanup”的基础顺序。

### 6.3 准确性判断

文档的能力分层方向基本准确，但作为实现规范仍不完整：

- `run 结束后 prune` 没有区分 agent process 返回、cell finalization 与 whole-run 完成；
- Provider Interface 列出 collection/cleanup，却没有规定相对 validator 的调用顺序；
- 当前版本没有新的权威 PRD，旧 PRD 与 Unicorn Current State 有版本漂移；
- diff 的 staged/untracked、容量和脱敏语义没有固定；
- normal 与 abnormal lifecycle 没有拆成独立交付范围。

所以，设计文档足以判断该能力属于当前版本；本文与当前 issue 05 已补齐实现所需的可执行约束。

## 7. 当前 codebase 的实现性质

### 7.1 已确认的调用事实

普通单轮路径在
[`kernel.py`](../../src/micro_eval/engine/kernel.py) 中执行：

```text
WorkspaceManager.prepare
→ AgentAdapter.invoke(cwd=prepared.path)
→ finally: WorkspaceManager.cleanup_workspace(prepared)
→ Artifact persistence
→ validate_cell(workspace_dir=prepared.path)
```

[`validator.py`](../../src/micro_eval/evaluation/validator.py) 已明确把 `file_exists` 和
command expectation 的默认范围设为 agent 的 workspace。因此不是 validator 缺少能力，
而是 Kernel 把已销毁的目录传给它。

Conversational helper 在返回到外层 `finally` 前已经完成 validation，所以同一 Kernel 中
两条路径的生命周期不同。两条路径还分别创建 Artifact、Evidence、Evaluation 和
CellResult，导致 finalization 规则复制。

### 7.2 终态 observation 与 Store 的代码事实

- [`providers/base.py`](../../src/micro_eval/engine/providers/base.py) 同时暴露
  `collect_artifacts()` 和 `collect_diff()`，但 Kernel 都没有消费。
- [`git_worktree.py`](../../src/micro_eval/engine/providers/git_worktree.py) 的 diff 仅执行
  `git diff --no-color`：不含 untracked 文件，输出捕获无界，也没有进入 ArtifactStore。
- provider 返回 ArtifactRef 的 Interface 违反 Environment 与 Artifact/Trace 的所有权。
- [`artifact_store.py`](../../src/micro_eval/store/artifact_store.py) 只能索引 run directory
  内已有文件；没有持久化 Environment observation 的 Interface。
- [`kernel.py`](../../src/micro_eval/engine/kernel.py) 直接写 `evaluation.json`，run 末尾又
  直接读取它；[`run_store.py`](../../src/micro_eval/store/run_store.py) 没有 normal cell 的
  完整 commit Interface。
- [`workspace.py`](../../src/micro_eval/engine/workspace.py) 把 setup exit code 固定为
  `None`，虽然 provider 内部已经得到返回值。

### 7.3 测试为何没有阻止问题

现有测试分别证明了 validator 能读取一个仍存在的目录、provider 能独立返回 tracked
diff、WorkspaceManager 能 cleanup，以及 E2E 结束后 workspace 已删除。但没有一个测试
穿过真实 Lifecycle Interface 验证：

```text
agent mutates workspace
→ observe terminal state
→ persist diff/evidence
→ validate live workspace
→ cleanup
→ commit result
```

这与 [testing guidelines](../engineering/testing-guidelines.md) 已要求的
“Kernel + Adapter + Workspace + Store” Integration 层不一致。

### 7.4 最终分类

| 范围 | 当前性质 | 分类 |
| --- | --- | --- |
| Workspace create、cwd、基础 snapshot | 主路径已接入 | 已实现 |
| 普通单轮 `file_exists` / command validation | validator 正确，Kernel 先删后验 | **错误实现** |
| Git diff / workspace observation | provider 局部存在，主路径未消费且语义不足 | **不完整实现** |
| 单轮与 conversational finalization | 两套顺序与结果组装 | **实现冲突** |
| setup outcome | provider 得到事实但 snapshot 丢弃 | **不完整实现** |
| evaluation/result persistence | Kernel 绕过 Store Interface | **架构冲突** |
| 真实正常 lifecycle 验收 | 只有分离测试 | **覆盖缺口** |

主标签仍是**错误实现**，因为已经声明的用户能力会产生确定性假失败。更完整的根因是：
若干局部能力没有在一个深 Module 中形成有序闭环，最后组合成错误生命周期。

## 8. 更新后的 issue 05 能否可靠形成修复方案

答案是：**能，在本文限定的本地 workspace 正常生命周期范围内可以。**

Issue 05 是当前任务契约；本文解释其设计依据。两者当前的一致性如下：

| 可靠性条件 | issue 05 当前约束 | 判断 |
| --- | --- | --- |
| 范围单一 | 只处理本地 workspace 的正常生命周期；异常、remote 与 UI 分发分别后置 | 已满足 |
| Module 归属明确 | Kernel 内部统一 lifecycle；Environment observation；Artifact 引用；Store commit | 已满足 |
| 顺序唯一 | checklist 固定 `prepare → observe → validate → cleanup → commit`，single/conversational 共用 | 已满足 |
| diff 可实现 | 固定 source HEAD、staged/unstaged/untracked、setup caveat、cap、脱敏和 validator 副作用 | 已满足 |
| 持久化不泄漏布局 | Environment 不创建 ArtifactRef，Kernel 不直接读写 evaluation 文件 | 已满足 |
| 验收可证伪 | 覆盖三种 workspace、两种 invocation 路径、真实 Store 与安全约束 | 已满足 |
| 文档不会再次漂移 | issue 明确要求同步 WorkspaceProvider 与 Artifact/Store ownership 的权威文档 | 已满足 |

实施者不再需要自行决定 cleanup 相对 validator 的位置、是否复制整个 workspace、
provider 是否生成 ArtifactRef，或是否顺带修复 wheel/UI 和异常恢复。剩余问题已经在
§9.2 明确为后续设计，不是 issue 05 的隐藏阻塞项。

## 9. 修复蓝图与架构缺失汇报

### 9.1 本次 P0 必须补齐的缺失

| 缺失 | 所属位置 | 是否新增顶层 Module | 处理 |
| --- | --- | --- | --- |
| 统一正常 cell lifecycle | Execution Kernel 内部 | 否 | 新增深 Module `engine/cell_lifecycle.py` |
| 终态 observation model / Interface | Environment | 否 | `WorkspaceObservation` + `observe_final()` |
| workspace observation 持久化 | Artifact/Trace | 否 | `persist_workspace_observation()` |
| cell evaluation/result commit | RunStore Implementation | 否 | `FinalizedCell` + `commit_cell()` |
| single/conversational common tail | Execution Kernel / Agent Adapter Seam | 否 | invocation outcome 后统一 finalization |
| 正常 lifecycle Integration/E2E 验收 | 测试架构 | 否 | 穿过真实 Lifecycle Interface |
| Provider 权威 Interface 对齐 | Environment / 架构文档 | 否 | 同步 Unicorn §3.4.4 与 runtime ownership |

建议实施顺序不是 TDD：

1. 先实现 `WorkspaceObservation`、setup outcome 与 provider Interface；
2. 再实现 ArtifactStore observation persistence 和 RunStore cell commit；
3. 然后提取 CellLifecycle，把 single/conversational 接入共同尾段；
4. 删除 Kernel 中直接 evaluation 文件读写和重复 finalization；
5. 最后按 §10 验证用户路径、Integration 与安全不变量。

### 9.2 已发现但不阻塞本次 P0 的缺失

1. **任意 workspace 文件的声明式归档策略缺失。** `blank/files` 没有天然 diff；当前
   TaskSpec 也没有 `artifact_paths` 或同类声明。当前修复只承诺 Adapter outputs、git
   diff 与 validation evidence，不应默认复制整个 workspace。若产品要求 cleanup 后复核
   任意文件内容，需要先补 Configuration/Task schema 与 Artifact selection policy。
2. **setup 后 prepared-state baseline 不足。** 当前终态 diff 相对 source `HEAD`，所以
   setup 的非 ignored 修改与 agent 修改不能被精确分离；CellSnapshot 也不能证明两个 cell
   的 setup 后文件树相同。issue 05 要求诚实 caveat，但纯 agent delta 与更强 same-start
   仍需要 Environment 定义有界 prepared tree baseline/digest。
3. **异常 lifecycle 状态与恢复缺失。** cancellation、hard crash、cleanup retry、lease、
   journal 和 reconcile 仍需要独立设计，见附录 A；它们不应潜入正常路径 P0。
4. **安装产物的 UI/serve 契约仍未决。** 这是分发/产品 Interface 问题，与 workspace
   lifecycle 没有共同实现 Seam，应另立 issue，不得继续塞入 issue 05。
5. **Construction Seam 仍偏浅。** 当前 Kernel 直接构造 AgentAdapter、WorkspaceManager 和
   ArtifactStore，而 Unicorn 目标设计要求 registry/constructor injection。CellLifecycle 的
   小 Interface 已提供测试面，但完整 composition-root 收敛可以独立跟进，不阻塞本次顺序修复。

架构层面的最终汇报是：**顶层 Module 没有缺失，内部深 Module 和跨 Module Interface
确实缺失。** 上述 P0 项如果不先补齐，单纯移动 cleanup 行只能修复一个症状，不能保证
single/conversational、diff、Store 与未来 provider Adapter 继续遵守同一顺序。

## 10. 实施完成后的验证矩阵

以下验证在实现完成后执行；它们是验收，不要求采用 TDD。

| 场景 | 必须验证的事实 |
| --- | --- |
| `blank` + `file_exists` | agent 创建文件；validator 判 present；cleanup 后目录不存在；result/evaluation/evidence refs 均可解析 |
| `files` + command | agent 修改 fixture；command 在同一 live workspace 看到修改；结果提交后 cleanup 为 cleaned |
| `git_repo` tracked 修改 | `workspace.diff` 包含 staged/unstaged 修改，ArtifactRef 有 digest/cap/redaction 状态 |
| `git_repo` untracked 文本文件 | diff 包含安全的新文件内容；ignored/binary/link/超限只产生 warning |
| setup 修改 source | diff 相对 source HEAD 并包含 setup 修改，同时 Evidence 明确记录 caveat，不宣称纯 agent delta |
| validator 有副作用 | observation 早于 validator；validator 创建的 sentinel 不出现在 validation 前终态 diff |
| agent 正常非零退出 | 仍产生 observation、process evidence、validation、CellResult 和正常 cleanup |
| conversational 正常路径 | 与单轮共用 observe/validate/cleanup/commit 尾段，conversation artifact 保持可引用 |
| RunRecord projection | evaluations 来自 `commit_cell()`，Kernel 不再扫描 `evaluation.json` |
| Decision | 只引用已提交 Evaluation/Evidence；无 workspace 绝对路径作为唯一证据 |
| 安全 | workspace 不越 project root；命令 argv-only；diff 写盘前脱敏；捕获与 Artifact 均有 cap |

至少有一条 Integration 测试必须使用真实 `WorkspaceManager`、本地 AgentAdapter、
ArtifactStore 与 RunStore，通过 `CellLifecycle.execute()` 完成完整闭环；不能继续只用四组
分离单元测试拼接信心。

## 附录 A：此前异常 workspace 生命周期分析原文

> 状态：历史分析，保留在固定文档中；本轮已明确不把它作为 issue 05 的范围或
> `ready-for-agent` 前置条件。下文最后关于“扩大 issue 05”的建议已被本次范围决策取代，
> 异常生命周期需要另立 issue。

结论：workspace 生命周期只被“局部考虑”，没有覆盖完整的中断语义。

更准确的分类是：

- 可控中断（Ctrl-C、task cancel、run timeout）：当前是**错误实现**。
- 不可控中断（SIGKILL、进程崩溃、机器宕机）：恢复机制基本**未实现**。
- prepare、persist、cleanup 的半失败：属于**不完整实现且存在冲突**。
- 整体上，workspace 还没有形成可恢复、幂等的生命周期闭环。

### A.1 实际验证结果

我跑了几条真实故障路径：

| 场景 | 当前结果 |
| --- | --- |
| agent 运行中 Ctrl-C | CLI 返回 130，但 agent 仍存活；workspace 已删除；`run.json` 永久停在 `running`，没有 CellResult |
| CLI 与 agent 被 SIGKILL | workspace 残留；`run.json` 停在 `running` |
| server 风格的 `asyncio.wait_for()` 超时 | Kernel task 结束，但 agent、workspace 和多个异步 task 仍在运行 |
| agent 包装器派生子进程 | timeout 只终止直接子进程；后代进程继续运行并占用 stdout/stderr 管道，adapter 无法按时返回 |
| `files` 复制或 setup 启动到一半失败 | 半成品 workspace 残留，而且没有注册到 `_prepared`，后续 cleanup 无法发现 |

根因可以直接从代码看到：

- Kernel 创建所有 cell task，但没有 run 级取消、统一 cancel-and-await 或异常终态持久化：
  [`kernel.py`](../../src/micro_eval/engine/kernel.py)。
- `CancelledError` 被继续抛出，随后 `finally` 直接删除 workspace：
  [`kernel.py`](../../src/micro_eval/engine/kernel.py)。
- Adapter 只有 timeout 分支的 `terminate → kill`，没有 cancellation 分支，而且只操作
  直接进程：[`adapter.py`](../../src/micro_eval/engine/adapter.py)。
- Run/Cell 状态模型没有 `cancelled`、`interrupted`、`not_started`：
  [`run.py`](../../src/micro_eval/models/run.py)。
- `run.json` 直接覆盖写入，没有原子 journal；中断后只能留下最初的 `running`：
  [`run_store.py`](../../src/micro_eval/store/run_store.py)。
- Provider 完成整个 create/setup 后才返回 handle；中途失败时 WorkspaceManager 没有资源
  身份可供回滚：[`git_worktree.py`](../../src/micro_eval/engine/providers/git_worktree.py)、
  [`workspace.py`](../../src/micro_eval/engine/workspace.py)。
- Server 的恢复只修正 queue job 状态，不收敛 run、cell workspace 或 agent 进程：
  [`queue.py`](../../src/micro_eval/server/queue.py)。当前 cancel 实际也是“run 完成后标记
  cancelled”，不是取消正在执行的 run：
  [`worker.py`](../../src/micro_eval/server/worker.py)。

### A.2 文档需要进一步修正的地方

现有文档的“Agent timeout、crash 或被取消”方向正确，但把四种不同性质的事件合在了
一起。

必须拆开：

- agent timeout：被测 agent 的有效评测结果，可以计入失败策略。
- agent crash：agent 已停止，可以收集部分证据并形成 error CellResult。
- 用户取消／SIGTERM：控制面事件，不能算作 agent 失败。
- runner crash／SIGKILL／宕机：没有机会执行 `finally`，只能依靠下次启动恢复。

当前生命周期顺序也需要拆成两个持久化屏障：

```text
provisioning
→ ready
→ running
→ quiescing：确认进程树或远端 session 已停止
→ finalizing：收集部分或完整终态证据
→ result_committed：持久化 CellResult，cleanup_status=pending
→ cleanup_pending
→ cleanup
→ cleaned | retained | cleanup_failed
→ closed：再次持久化 cleanup outcome
```

不能在 cleanup 前声称 cleanup outcome 已经完成；也不能等 cleanup 完成后才第一次持久化
CellResult。否则崩溃发生在两者之间时，无法判断应该恢复取证还是只重试清理。

### A.3 各类边界情况的期待行为

| 中断点 | 应有行为 |
| --- | --- |
| 创建目录、复制 fixture、建立 worktree、setup 中断 | Provider 内部事务性回滚；失败资源已登记，允许后续 reconcile |
| agent 运行中取消 | 停止调度新 cell；终止并等待整个进程树；保存有界的部分输出；再 cleanup |
| configured agent timeout | 终止进程树，记录 `timeout`；部分证据可用；其他 cell 可继续 |
| validator/judge/finalization 崩溃 | 保留 AdapterResult 和已写 artifact；记录 `finalization_error`；之后 cleanup |
| JSON/artifact 写到一半崩溃 | 使用临时文件加原子替换；journal 保持在可重试阶段 |
| cleanup 失败 | 已完成结果保持不变；标记 `cleanup_pending/failed`，可重试，不能谎报 `cleaned` |
| cleanup 完成但状态尚未写回就崩溃 | 恢复时发现受管 workspace 已不存在，幂等地补记 `cleaned` |
| SIGKILL／宕机 | 下次启动扫描非终态 lease，确认原 owner 已死亡，再完成取证或 cleanup |
| 并发 run 被取消 | 已完成 cell 保留；运行中 cell 取消；未启动 cell 明确标记 `not_started` |
| 远端断线 | 使用持久化 sandbox/session ID 重新连接或取消；状态未知时保留 `cleanup_pending` |

### A.4 推荐的模块设计

应在 ExecutionKernel 与 Adapter/WorkspaceProvider/Store 的 Seam 上增加一个深 Module，
例如 `CellLifecycle`。

它的 Interface 保持很小：

```python
async def execute(cell, context) -> CellOutcome
async def reconcile_stale() -> RecoveryReport
```

Implementation 内部统一负责：

- workspace lease 与所有权 journal；
- prepare 失败回滚；
- agent 结构化并发与进程树终止；
- 最终化、证据提交、cleanup 的严格顺序；
- cancellation 和 hard-crash recovery；
- 幂等 cleanup 与重试。

Adapter 的关键 Interface 不变量应是：

> `invoke()` 无论正常返回、timeout 还是被取消，在控制权交还前，都不得留下仍属于本次
> invocation 的活动进程或远端 session。

本地实现需要独立进程组／session，并对整组执行
`TERM → grace → KILL → wait → drain`；Windows 使用 Job Object。WorkspaceProvider 的
cleanup 应返回结构化 `CleanupResult`，不能内部吞掉异常后让上层误记为 `cleaned`。

### A.5 建议实施顺序

1. 先修复安全和正确性：进程树终止、cancel-and-await、run 中断终态持久化、prepare
   回滚、finalization-before-cleanup。
2. 引入每 cell 的原子 lifecycle journal、workspace ownership token 和幂等 cleanup。
3. 增加启动时 reconcile，以及带 `--dry-run` 的 orphan workspace 检查/清理命令。
4. 把 server cancel、run timeout、worker crash recovery 接入同一生命周期。
5. 最后接远端 provider 的 reattach/cancel/cleanup 协议。

Decision 语义也要明确：configured agent timeout 可以作为评测结果；用户取消、runner
崩溃和未启动 cell 必须排除出胜负计算，并把整个 Decision 标为
incomplete/inconclusive。

因此，现有 issue 05 应扩大为“正常与异常路径共同满足 workspace 生命周期不变量”，
而不是只修 cleanup-before-validation。否则正常路径修好后，Ctrl-C、server timeout 和
hard crash 仍会继续制造活进程、孤儿 workspace 和永久 `running` 的 run。

本轮处置：上段是保留的历史建议，已被“issue 05 只修本地 workspace 的正常生命周期、异常
生命周期另立 issue”的当前范围决策取代。
