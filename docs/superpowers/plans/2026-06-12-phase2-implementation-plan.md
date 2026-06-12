---
title: "Phase 2 Implementation Plan: trace_enhanced.v1"
doc_type: spec
status: draft
created_at: 2026-06-12T10:30+08:00
updated_at: 2026-06-12T10:30+08:00
owner: micro-eval maintainers
source_of_truth: false
profile: trace_enhanced.v1
tags:
  - phase2
  - implementation-plan
  - langfuse
  - aggregation
  - micro-eval
related:
  - docs/superpowers/specs/2026-06-02-unicorn-design.md
  - docs/superpowers/specs/2026-06-02-mvp-profile.md
  - docs/superpowers/specs/2026-06-02-test-architecture.md
  - docs/engineering/security-guidelines.md
---

# Phase 2 Implementation Plan: `trace_enhanced.v1`

> **执行说明**：本计划遵循项目硬规则——禁止 TDD。每个里程碑的开发顺序为：
> 理解规格 → 模块/接口设计 → 实现可运行的垂直切片 → 用验收测试和真实产物验证。
> 测试仅作为验收、回归与契约保护手段。
> 每个里程碑动手前必须读 `docs/engineering/security-guidelines.md`，
> 完成后必须逐条过其 Code Review Checklist——安全验收与功能验收同为合并门槛。

**目标**：在不改变 MVP 契约的前提下，将 Artifact/Trace、Evaluation、Decision 三层从 L1 升级到 L2，交付 CLAUDE.md 路线图定义的 Phase 2 四项能力：repetitions 统计聚合、Langfuse trace 接入、复盘页、成本分析。

**架构**：所有升级都是模块内部 maturity 提升（Unicorn §8），只补充字段或能力，不改变既有契约。Langfuse 经适配层（`TraceProvider` 接口）接入，未配置时降级运行。

**权威来源**：模块契约与字段定义以 `2026-06-02-unicorn-design.md` 为准（本计划引用章节号，不重述定义）。本计划只规定实施顺序、文件归属与验收标准。

---

## 1. 范围与接入顺序

CLAUDE.md 要求底座**串行接入**。Phase 2 拆为四个可独立交付的里程碑，依赖关系决定顺序：

```text
P2-a 统计聚合 + decision.json 独立化   （纯内部，无外部底座，风险最低）
  ↓ 成本数据需要有地方展示与聚合
P2-b Trace 适配层 + Langfuse 接入      （第一个外部底座，可选降级）
  ↓ 复盘页消费 trace + cost 数据
P2-c 复盘页 + 成本分析 UI              （展示层，消费 a/b 的产出）
  ↓ （可延后）
P2-d DeepEval custom metric           （第二个外部底座，stretch goal）
```

每个里程碑交付后可暂停，不阻塞 main 的可发布状态。

### Phase 2 明确不含（登记备查，防止范围蔓延）

以下属于 Unicorn 已有挂载点但本计划不实施，触发条件见各条：

- **ATIF / file-based trace import**（Artifact/Trace L2 的另一形态）——当出现需要导入第三方 agent trajectory 的真实用例时再排期。
- **Critique run（`micro-eval critique`）**——依赖 LLM judge 基础（P2-d）成熟后再设计。
- **Task package 目录格式**——Asset L2，等 coding-agent benchmark 场景出现。
- **Deterministic subset（n_tasks/sample_seed）**——Configuration L2，等任务库规模超过手工管理能力。
- **Docker sandbox / network allowlist / 远程 adapter**——Phase 3。
- **统计显著性检验 / 置信区间**——Decision L3，pass@k + low-confidence caveat 已满足当前决策需求。

---

## 2. 模块升级总表

| Module | MVP (L1) | Phase 2 (L2) | 契约不变项 |
|--------|----------|--------------|-----------|
| Artifact/Trace | 本地 artifact index + process-level trace | + `TraceRef`、`TraceProvider` 接口、LangfuseProvider | `ArtifactRef` / `EvidenceItem` 形状 |
| Evaluation | validation + 人工评分 | + `AggregationResult` 独立化、pass@k/pass^k 默认指标；(stretch) DeepEval judge | `EvaluationResult` + evidence refs |
| Decision | run.json 内嵌 decision | + 独立 `decision.json`、cost 维度、复盘下钻 | DecisionStatus taxonomy + caveats |
| 展示层 | Run List / Matrix / Cell Detail | + 复盘页、CostPanel、TraceViewer | API 经 RunStore，不直接拼路径 |

---

## P2-a：repetitions 统计聚合 + decision.json 独立化

### 规格依据

- pass@k 适用条件：Unicorn §5.7（权威定义，四条边界规则 + `denominator_policy`）。
- AggregationResult 独立化：mvp-profile §4.9 GAP 5 stub 的兑现。
- decision.json 拆分：mvp-profile §4.9 GAP 7——"Phase 2 将其拆为独立 decision.json + 分配 decision_report_id，无需迁移旧数据（直接从 run.json['decision'] 提取）"。

### 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `src/micro_eval/decision/aggregation.py` | pass@k / pass^k / pass rate / latency / cost 聚合计算，纯函数 |
| 修改 | `src/micro_eval/models/decision.py` | 增加 `AggregationResult`、`DecisionReport`（含 `decision_report_id`）Pydantic 模型 |
| 修改 | `src/micro_eval/decision/summary.py` | verdict 计算消费 `AggregationResult`；保持 guarded decision 行为 |
| 修改 | `src/micro_eval/store/run_store.py` | 写 `decision.json`；读取时兼容旧 run（fallback 到 `run.json["decision"]`） |
| 修改 | `src/micro_eval/cli/report.py` | 文本矩阵增加 pass@k 列与 low-confidence caveat |
| 修改 | `ui/src/lib/schema.ts` | zod schema 同步 `AggregationResult` / `decision.json` |
| 修改 | `ui/src/components/ComparisonTable.tsx`、`DecisionSummary.tsx` | 展示 pass@k 与聚合统计 |
| 新建 | `tests/unit/test_aggregation.py` | 聚合纯函数的验收用例（边界规则四条各一例） |
| 修改 | `tests/e2e/test_p0b_reproducibility_flow.py` 或新建 e2e | repetitions>1 全流程验收 |

### 核心契约（实现时以此为准）

```python
# src/micro_eval/models/decision.py (additions)
class AggregationResult(BaseModel):
    schema_version: str = "1.0"
    per_configuration: dict[str, ConfigurationStats]

class ConfigurationStats(BaseModel):
    n_cells: int
    n_successful: int
    pass_rate: float | None          # None when no binary pass/fail available
    pass_at_k: dict[int, float] | None   # k -> estimate; only for binary outcomes
    pass_hat_k: dict[int, float] | None  # pass^k (all-k-succeed)
    mean_latency_ms: float | None
    median_latency_ms: float | None
    total_cost: CostMetric | None
    denominator_policy: Literal["include_failed", "exclude_failed"]
    caveats: list[str]               # e.g. ["low_sample"] when successful reps < 3

class DecisionReport(BaseModel):
    schema_version: str = "1.0"
    decision_report_id: str          # f"{run_id}::decision::{compact_ts}"
    verdict: DecisionStatus
    confidence: Literal["high", "medium", "low"]
    evaluation_refs: list[str]
    evidence_refs: list[str]
    caveats: list[str]
    aggregation: AggregationResult
    timestamp: str                   # compact format, e.g. "20260612T103000Z"
```

pass@k 计算的硬边界（违反任一条即验收失败）：

1. 只对 binary pass/fail 计算；多维 rubric score 不默认计算。
2. 失败/缺失 cell 按 `denominator_policy` 处理，默认 `include_failed`。
3. successful repetitions < 3 时必须附带 `low_sample` caveat。
4. repetitions=1 时 pass@1 ≡ pass rate，矩阵列不重复展示。

### 实施步骤

1. **设计核对**：重读 Unicorn §5.7 与 mvp-profile §4.9，确认上述模型字段与权威定义无冲突；如发现冲突，先改权威 spec 再动代码（CLAUDE.md 硬规则）。
2. **实现垂直切片**：`aggregation.py` 纯函数 → models → summary 消费 → run_store 写 `decision.json` → CLI report 展示。切片完成的标志：对一个 repetitions=3 的本地 mock run，`micro-eval report` 能输出 pass@k。
3. **UI 同步**：zod schema → ComparisonTable/DecisionSummary。
4. **验收**：见下。

### 验收标准

```bash
uv run pytest -q                          # 全部通过（含新增聚合用例）
uv run python examples/run-example.py     # 示例 run 正常
cd ui && npm run lint && npm run build
```

- 用 repetitions=3 的 mock eval 跑一次真实 run：`.micro-eval/runs/{run_id}/decision.json` 存在，含 `decision_report_id` 与 `aggregation`；`micro-eval report` 显示 pass@k 与 low-confidence caveat。
- 对一个 v0.1.3 产生的旧 run 执行 `micro-eval report --run <old_id>`：不报错，verdict 从 `run.json["decision"]` 读取（向后兼容）。
- 契约测试：`DecisionReport.verdict != inconclusive/not_comparable` 时 `evaluation_refs` 非空（沿用 mvp-profile §10 既有断言）。
- 安全：本里程碑无 subprocess/env 变更，但仍须过 security checklist（artifact 持久化路径未变更、无新外发数据）。

---

## P2-b：Trace 适配层 + Langfuse 接入（可选降级）

### 规格依据

- TraceProvider 与 Langfuse 定位：Unicorn §5.6（Future levels）、§14（registry 注入模式 `registry.register_traces(LangfuseProvider(...))`）。
- Cost 数据优先级阶梯：Unicorn §9（约 line 1883）：
  1. Langfuse trace 中的 cost（已配置且 agent 上报 trace_id）→ 精确
  2. agent 通过约定 env/文件自报 cost → 精确
  3. Langfuse 有 token 数无 cost → token × 单价估算 → 近似
  4. 都没有 → `CostMetric(amount=None)` + report 显示"成本数据不可用"警告
- trace_id 注入已在 MVP 完成（`MICRO_EVAL_TRACE_ID` env），本里程碑只做收集端。

### 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `src/micro_eval/trace/__init__.py` | 包入口 |
| 新建 | `src/micro_eval/trace/provider.py` | `TraceProvider` Protocol + `TraceRef` 关联逻辑 |
| 新建 | `src/micro_eval/trace/process_provider.py` | 内建 process-level provider 正式化（wall clock、exit code、trace_id——从 kernel/runner 中抽出，行为不变） |
| 新建 | `src/micro_eval/trace/langfuse_provider.py` | Langfuse SDK 封装；导入失败或未配置时不实例化 |
| 修改 | `src/micro_eval/models/artifact.py` | 增加 `TraceRef` 模型 |
| 修改 | `src/micro_eval/engine/kernel.py` | cell 完成后调用注入的 provider 收集 trace/cost（接口注入，不 import langfuse） |
| 修改 | `src/micro_eval/engine/runner.py` | run 启动时按配置组装 providers |
| 修改 | `src/micro_eval/config/loader.py` | eval.yaml 增加可选 `trace:` 块（enabled/provider） |
| 修改 | `src/micro_eval/decision/aggregation.py` | cost 聚合消费 cost ladder 的输出与 `source` 标注 |
| 修改 | `pyproject.toml` | `langfuse` 加入 optional dependency group `[trace]` |
| 新建 | `tests/unit/test_trace_provider.py` | 降级行为 + cost ladder 优先级用例 |

### 核心契约

```python
# src/micro_eval/trace/provider.py
class TraceRef(BaseModel):
    trace_id: str                    # equals MICRO_EVAL_TRACE_ID injected at invocation
    provider: str                    # "process" | "langfuse"
    external_url: str | None         # deep link into Langfuse UI when available
    cost: CostMetric | None
    summary: dict | None             # provider-specific, must be redacted

class TraceProvider(Protocol):
    name: str
    def collect(self, cell: RunCell, result: ExecutionResult) -> TraceRef | None: ...
```

配置与降级规则：

- Langfuse 凭证仅从环境变量读取（`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`），**不写入 eval.yaml、不写入任何 artifact/run.json**。
- 未安装 langfuse 包、未设置凭证、或网络失败：全部降级为 process provider，run 正常完成，report 标注 cost source。降级不是错误，不产生非零 exit code。
- `TraceRef.summary` 持久化前过 `SecretRedactor`（与 stdout/stderr 同一边界）。

### 实施步骤

1. **先读安全规范**：本里程碑触碰 env 注入与**首个外发数据通道**（trace 上报到 Langfuse），是 Phase 2 安全敏感度最高的改动。确认 security-guidelines 对外发内容的要求；trace 上报内容（prompt/stdout 摘要）必须先脱敏。
2. **抽取 process provider**：把现有 kernel/runner 中的 trace/cost 收集逻辑抽到 `trace/process_provider.py`，行为完全不变，全部既有测试通过——这是无风险的重构切片。
3. **实现 TraceProvider 接口 + Langfuse provider**：kernel 只依赖 Protocol。
4. **cost ladder**：在 aggregation 中按四级优先级取值并标注 `CostMetric.source`。
5. **验收**。

### 验收标准

- 未配置 Langfuse：`uv run pytest -q` 全过，示例 run 正常，report 显示"成本数据不可用"。
- 配置假凭证（不可达 host）：run 正常完成，trace 降级，stderr 有一条 warning，artifact 中无凭证泄露。
- 单元测试覆盖：cost ladder 四级各一例；`grep` 验证 `LANGFUSE_SECRET` 值不出现在 `.micro-eval/` 任何文件。
- 契约测试：kernel 不直接 import langfuse（`grep -r "import langfuse" src/micro_eval/engine/` 为空）。
- security checklist 逐条通过，交付报告说明 secrets redaction、workspace 边界、shell interpolation 三项。

---

## P2-c：复盘页 + 成本分析 UI

### 规格依据

- Viewer 下钻链：mvp-profile §11——"Run → Configuration/Task heatmap → Cell → Artifact → Trajectory → Validation"。
- Decision Surface 兑现义务五条：Unicorn §5.8（可比性裁决可见、证据链可导航、脱敏强制、样本不足合法、失败 cell 透明）——本里程碑的验收 checklist。
- API 约束：Route Handler 经 RunStore 接口读数据，不直接拼路径（Unicorn §15.1）。

### 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `ui/src/app/run/[id]/review/page.tsx` | 复盘页：verdict + caveats + heatmap + 成本对比 + 下钻入口 |
| 新建 | `ui/src/components/CostPanel.tsx` | per-configuration cost/latency 对比（含 source 与"不可用"态） |
| 新建 | `ui/src/components/TraceViewer.tsx` | TraceRef 展示：duration、cost、外链 Langfuse（存在时） |
| 新建 | `ui/src/components/MatrixHeatmap.tsx` | Task × Configuration pass-rate 热力格，点击进 cell |
| 修改 | `ui/src/app/api/runs/[id]/route.ts` | 响应中带 `decision.json` 聚合数据 |
| 新建 | `ui/src/app/api/runs/[id]/cells/[cellId]/trace/route.ts` | 返回 cell 的 TraceRef |
| 修改 | `ui/src/lib/schema.ts`、`lib/api.ts` | zod 同步 TraceRef/DecisionReport |
| 修改 | `ui/src/components/CellDetail.tsx` | 挂 TraceViewer + 评分/验证证据并列 |
| 新建 | `ui/src/lib/__tests__/`（或既有 vitest 位置） | schema 契约 + 组件渲染用例 |

### 实施步骤

1. **数据通路先行**：API route 返回 decision/trace 数据（RunStore 接口扩展在 P2-a/b 已就位），用 `contractFixtures.ts` 固定契约样例。
2. **复盘页垂直切片**：先做 verdict + CostPanel + heatmap 的静态可用版本，真实 run 数据可见即为切片完成。
3. **下钻链补全**：heatmap → cell → artifact/trace 导航不断链。
4. **验收对照 Decision Surface 五条义务**逐条检查。

### 验收标准

- `cd ui && npm run lint && npm run build && npx vitest run` 全过。
- 用 P2-b 产出的真实 run 手工走查：从 verdict 出发可下钻到 task → cell → artifact → trace → cost，无断链。
- `not_comparable` / `inconclusive` 的 run 在复盘页不显示 winner；失败 cell 在 heatmap 上有标记与原因。
- UI 渲染内容均来自已脱敏 artifact/evidence；无组件直接读文件系统。

---

## P2-d（stretch）：DeepEval custom metric / LLM judge 初步

> 本里程碑可整体顺延，不阻塞 Phase 2 收口。开工前需补一份 judge prompt 与 rubric 映射的小型设计文档（挂载点：Unicorn §4.4 Mode 3）。

### 边界（先于实现锁定）

- DeepEval **仅作评分库**，不用其 test runner（CLAUDE.md 锁定决策）。
- `evaluator: "llm_judge"` + `evaluator_meta`（model、temperature）写入 `EvaluationResult`——MVP schema 已预留，无 schema 变更。
- LLM judge **不能覆盖 deterministic 关键失败**（Unicorn §5.7 Must not bypass）：validation 失败的 cell，judge 分数只能作为补充 evidence，verdict 计算中 deterministic 失败优先。
- judge rationale 作为 `judge_rationale` 类型 EvidenceItem 持久化。

### 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `src/micro_eval/evaluation/llm_judge.py` | DeepEval custom metric 封装，输出 EvaluationResult |
| 修改 | `src/micro_eval/evaluation/validator.py` 调用方（`engine/runner.py`） | run 后评估管线挂载 judge（配置开启时） |
| 修改 | `src/micro_eval/config/loader.py` | eval.yaml 可选 `judge:` 块 |
| 修改 | `pyproject.toml` | `deepeval` 入 optional group `[judge]` |
| 新建 | `tests/unit/test_llm_judge.py` | mock judge：不覆盖 deterministic 失败的契约用例 |

### 验收标准

- 未安装/未配置 deepeval：一切行为与 P2-c 交付态完全一致。
- mock judge 用例证明：validation 失败 + judge 高分 → verdict 不得为 `improved`。
- judge 的 API key 走 `MICRO_EVAL_SECRET_*` 既有 secrets 通道，redaction 验证同 P2-b。

---

## 统一交付门槛（每个里程碑）

1. `uv run python -m compileall src/micro_eval tests`
2. `uv run pytest -q` 全过（不得为通过测试缩窄实现）
3. `cd ui && npm run lint && npm run build`（涉及 UI 时 + `npx vitest run`）
4. `uv run python examples/run-example.py` 示例冒烟
5. `grep -RInE 'create_subprocess_shell|shell=True' src tests ui examples` 零匹配
6. security-guidelines Code Review Checklist 逐条通过，交付报告说明 secrets redaction / workspace 边界 / shell interpolation 三项
7. 按 documentation-standard 写 dev log（`docs/dev/log/YYYY-MM-DD-HHMM-dev-log-<topic>.md`）
8. dev 分支提交，功能完整后 merge 到 main；版本号按里程碑 bump（建议 P2-a→0.2.0，之后 0.2.x 递增）

---

## 风险登记

| 风险 | 缓解 |
|------|------|
| Langfuse SDK 迭代快，接口漂移 | 全部 Langfuse 依赖收敛在 `trace/langfuse_provider.py` 单文件适配层内 |
| trace 上报造成数据外发泄露 | 上报前过 SecretRedactor；P2-b 验收含泄露 grep；凭证只走 env |
| pass@k 在低样本下误导决策 | 硬性 low_sample caveat + repetitions<3 时 confidence 上限 low |
| decision.json 拆分破坏旧 run 读取 | run_store 读取 fallback 到 `run.json["decision"]`，e2e 含旧数据用例 |
| DeepEval 引入拖慢评估管线 | optional dependency + 配置默认关闭；judge 失败不影响 deterministic 结果 |
| UI 范围蔓延（编辑器/实时进度） | 沿用 mvp-profile §7 "UI 不做"清单，Phase 2 不解禁 |
