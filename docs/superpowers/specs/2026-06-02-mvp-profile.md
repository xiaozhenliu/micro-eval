---
title: "MVP Profile: mvp.local_pairwise.v1"
date: 2026-06-02
status: active
type: implementation-guide
parent: "[[2026-06-02-unicorn-design]]"
profile: mvp.local_pairwise.v1
tags:
  - mvp
  - implementation
  - micro-eval
---

# MVP Profile: `mvp.local_pairwise.v1`

本文档是 Unicorn 模块化架构在 MVP 阶段的**可执行投影**。它不重新定义架构，
而是声明每个模块的选择等级、实现范围、必须遵守的契约，以及从当前 legacy v0.1.0 迁移的具体步骤。

**前置阅读**：`2026-06-02-unicorn-design.md` Part I（§1–§10）。
本文档中的模块名、契约名、Stable ID 规则均以该文档为权威定义。

---

## 1. MVP 目标

用户能在 10 分钟内完成：

```
定义 Tasks → 配置 Configurations → 发起 Run → 在矩阵对比中得出结论
```

MVP 回答的核心问题：**在同一起点、同一任务集下，这次改动变好了、变差了，还是样本不足 / 不可比 / 需要人工判断？**

结论必须可溯源（每个 DecisionStatus 都链接到 task → result → EvidenceItem → artifact / score）。

---

## 2. Profile 选择总表

| Module | Level | MVP 实现 | Must not bypass |
|--------|:-----:|----------|-----------------|
| Asset Layer | L0→L1 | 本地 YAML tasks + inline rubric | `task_id` / `rubric` hash |
| Configuration Layer | L1 | 显式 Configuration 模型，默认 2 列 pairwise，schema 支持 ≥2 列矩阵 | `configuration_id` / repetition identity |
| Execution Kernel | L1 | asyncio subprocess, timeout, 并行 | RunPlan → ExecutionResult shape |
| Agent Adapter Layer | L1 | 本地 CLI adapter, declared I/O | AgentInvocation 契约 / safe argv |
| Environment/Reproducibility | L1 | git worktree + workspace snapshot | SameStartSnapshot |
| Artifact/Trace Layer | L1 | 本地 `.micro-eval/` artifact index | ArtifactRef / EvidenceItem |
| Evaluation Layer | L0+L1 | validation + 人工评分 | EvaluationResult + evidence refs |
| Decision Layer | L0+L1 | 矩阵视图 + evidence-linked summary | DecisionStatus taxonomy + caveats |

---

## 3. 用户旅程（Golden Path）

```text
1. micro-eval init          → 生成 eval.yaml 骨架
2. 编辑 eval.yaml           → 定义 tasks + configurations（默认 baseline/candidate 两列；可声明 ≥2 个被测 Configuration）
3. micro-eval run           → 执行 Tasks × Configurations × Repetitions
4. micro-eval report        → CLI 输出矩阵摘要
5. micro-eval ui            → 启动 Next.js dev server (localhost:3000)
6. 查看 ResultMatrix        → 逐 cell 查看 artifact、人工评分
7. 得出结论                 → improved / regressed / mixed / inconclusive / not_comparable / needs_human_review
```

**CLI 接口规格**：

| 命令 | 行为 | 关键参数 |
|------|------|----------|
| `micro-eval init` | 在当前目录生成 `eval.yaml` 骨架 + `tasks/` 目录 | `--force` 覆盖已有 |
| `micro-eval run` | 执行 eval，结果写入 `.micro-eval/runs/` | `--config <path>`（默认 `./eval.yaml`）、`--max-concurrency <n>`（默认 4）、`--dry-run`（只打印 RunPlan 不执行） |
| `micro-eval report` | 输出最近一次 run 的文本矩阵摘要 | `--run <run_id>`（指定 run）、`--format text|json` |
| `micro-eval ui` | 启动 Next.js dev server | `--port <n>`（默认 3000） |
| `micro-eval list` | 列出所有 runs | 无 |

**Config 查找规则**：`--config` > `$MICRO_EVAL_CONFIG` env > `./eval.yaml` > error。

**错误行为**：所有 CLI 命令在失败时输出结构化错误（JSON to stderr if `--format json`），exit code 非零。

---

## 4. 模块逐项规格

### 4.1 Asset Layer（L0→L1）

**实现范围**：
- 本地 YAML 定义 tasks（prompt + workspace + expectations + rubric）
- Rubric 可内联于 task 或独立文件引用
- 每个 task 必须有 `task_id`（用户可读 slug）
- Run 开始时生成 asset snapshot（task 文件 content hash）
- Task 中 `workspace.ref`（branch/tag）在 Run 启动时解析为 commit hash；snapshot 记录 hash 而非 ref 名
- `task_revision_id` = task YAML 整体 hash（包含内联 rubric）；若 rubric 为外部文件引用，则 hash 计算包含引用文件内容

**数据模型**：
```yaml
# tasks/code-review.yaml
task_id: code-review-basic
prompt: "Review the following code for bugs..."
workspace:
  type: git_repo
  repo: ./fixtures/sample-project
  ref: main
expectations:
  - type: exit_code
    value: 0
  - type: contains
    target: stdout
    value: "bug"
rubric:
  dimensions:
    - name: completeness
      scale: [1, 5]
    - name: accuracy
      scale: [1, 5]
```

**契约**：`task_id` + content hash 构成 `task_revision_id`，传递给 Execution Kernel。

---

### 4.2 Configuration Layer（L1）

**实现范围**：
- `eval.yaml` 中声明 configurations 数组（每项 = 矩阵的一列）
- 每个 Configuration = AgentSpec + SkillSpec(可选) + WorkspaceSpec + params + repetitions
- 矩阵展开：Tasks × Configurations × Repetitions → RunPlan
- baseline/candidate 只是 role label，不是特殊数据结构

**数据模型**：
```yaml
# eval.yaml
configurations:
  - id: claude-code-v2
    role: baseline
    agent:
      agent_id: claude-code-v2       # stable agent identity (stub for Phase 2 versioning)
      command: ["claude", "--model", "sonnet"]
      input_mode: stdin
      output_mode: stdout
      timeout: 120
    repetitions: 3

  - id: cursor-agent
    role: candidate
    agent:
      agent_id: cursor-agent         # stable agent identity
      command: ["cursor-cli", "run"]
      input_mode: file
      output_mode: directory
      timeout: 120
    repetitions: 3

tasks:
  - tasks/code-review.yaml
  - tasks/refactor.yaml
```

**契约**：`configuration_id` 由 agent+skill+env+params 的 canonical digest 派生（MVP 可直接用声明的 `id` 字段）。

**EvaluationContract（最小形态）**：
```python
@dataclass
class EvaluationContract:
    comparison_subject: str | None     # e.g. "skill prompt v2 vs v1"
    task_set_version: str              # task_ids + task_revision_ids 的 digest
    success_criteria: list[str]        # human-readable criteria, copied into report
    budget: dict | None                # max_cost / max_duration / max_cells, MVP 可为 None
    decision_threshold: float | None   # MVP 默认 None（无自动判定阈值）
    inconclusive_policy: Literal["warn", "block"]  # MVP 默认 "warn"
    min_repetitions: int               # MVP 默认 1
    required_evaluators: list[str]     # MVP 默认 ["validator"]
    denominator_policy: Literal["include_failed", "exclude_failed"]  # 默认 "include_failed"
```

MVP 行为：`EvaluationContract` 随 `eval.yaml` 声明，不声明时使用上述默认值。`decision_threshold=None` 表示不做阈值驱动的自动 winner；`micro-eval report` 仍可输出矩阵、Basic Honest Stats、caveats，并在缺少足够人工评分或明确阈值时给出 `needs_human_review` / `inconclusive`，而不是伪造 `improved` / `regressed`。`inconclusive_policy="warn"` 表示样本不足时输出 `inconclusive` verdict + warning，不阻塞 report 生成。

---

### 4.3 Execution Kernel（L1）

**实现范围**：
- 将 RunPlan 展开为 RunCell 列表
- asyncio 并行执行（受 max_concurrency 限制）
- 每个 RunCell 调用 Agent Adapter，收集 AdapterResult
- timeout 硬中断 + exit code 记录
- 结果增量写入 `.micro-eval/runs/{run_id}/`（cell 完成即写，不等全部结束）
- 单个 cell 失败不影响其他 cell

**关键接口**：
```python
RunPlan → list[RunCell]
RunCell = (task_id, configuration_id, repetition_index)

@dataclass
class ExecutionResult:
    run_cell_id: str
    exit_code: int
    duration_ms: int
    adapter_result: AdapterResult
    cost: CostMetric | None       # None if agent doesn't report cost
    error: str | None
```

**Must not bypass**：Execution Kernel 不直接构造 agent command，必须通过 AgentInvocation。

---

### 4.4 Agent Adapter Layer（L1）

**实现范围**：
- 统一调用协议：`AgentSpec → AgentInvocation → AdapterResult`
- input_mode: `stdin` | `file`（禁止 shell 字符串插值）
- output_mode: `stdout` | `file` | `directory`
- 安全 argv 构建（列表形式，不经过 shell）
- env allowlist（只传白名单环境变量）
- secret redaction 边界（secrets 注入 env 但不进 artifact）
- exit code → 结构化错误分类（success / timeout / crash / nonzero）

**output_mode 契约**：
- `stdout`：agent 输出到 stdout，AdapterResult.stdout 即为结果
- `file`：agent 输出到 `$MICRO_EVAL_OUTPUT_FILE`（Kernel 注入 env），AdapterResult.output_artifacts 包含该文件
- `directory`：agent 输出到 `$MICRO_EVAL_OUTPUT_DIR`（Kernel 注入 env），AdapterResult.output_artifacts 列出目录内所有文件

**关键接口**：
```python
@dataclass
class AgentInvocation:
    argv: list[str]           # safe, no shell interpolation
    input_payload: str | Path # stdin content or file path
    input_mode: Literal["stdin", "file"]
    output_mode: Literal["stdout", "file", "directory"]
    timeout_seconds: int
    env: dict[str, str]       # allowlisted only
    workspace_path: Path
    trace_id: str             # injected as MICRO_EVAL_TRACE_ID env var

@dataclass
class AdapterResult:
    exit_code: int
    stdout: str
    stderr: str
    output_artifacts: list[Path]  # for directory mode
    duration_ms: int
    error_class: Literal["success", "timeout", "crash", "nonzero"]
    trace_id: str             # echo back for Artifact/Trace correlation
    output_truncated: bool    # True if stdout/stderr/artifacts hit size cap
```

**Output Cap Guardrail**（Unicorn §9 must-have）：
- `max_output_bytes`：单个 stdout/stderr 的读取上限，默认 10MB。超限时截断并标记 `output_truncated=True`
- `max_artifact_size_bytes`：单个 output artifact 文件的上限，默认 50MB。超限时跳过该文件并在 manifest 中记录 `skipped_oversized`
- 可在 eval.yaml 的 `guardrails:` 块中覆盖默认值
- 防御场景：agent 无限输出循环、cat 大文件、生成 GB 级 artifact

`trace_id` 派生规则：`f"{run_id}--{task_id}--{config_id}--rep{n}"`，由 Execution Kernel 生成后注入 AgentInvocation。

**与 legacy 的区别**：当前 v0.1.0 用 `asyncio.create_subprocess_shell` + 字符串命令。MVP 必须迁移为 `create_subprocess_exec` + argv 列表。

---

### 4.5 Environment / Reproducibility（L1）

**实现范围**：
- workspace 类型：`git_repo`（git worktree 隔离）| `blank`（临时空目录）| `files`（复制指定文件）
- **Run 级**：记录 intended SameStartSnapshot（期望起点）
- **Cell 级**：每个 RunCell 执行时记录 observed CellSnapshot（实际起点）
- Snapshot 包含：repo commit、dirty state、config hash、Configuration digests、Python version、setup commands digest、timestamp
- git worktree 创建与清理（run 结束后 prune）
- setup_commands 在 workspace 内执行
- Task 中的 `workspace.ref`（branch/tag）在 run 启动时解析为 commit hash，snapshot 记录 hash 而非 ref 名

**SameStartSnapshot 结构**（Run 级 intended）：
```python
@dataclass
class SameStartSnapshot:
    workspace_type: str
    git_commit: str | None        # resolved hash, NOT branch name
    git_dirty: bool
    config_hash: str              # eval.yaml content hash
    configuration_digests: dict[str, str]  # config_id -> agent+skill+env+params canonical JSON digest
    python_version: str
    setup_commands_digest: str | None
    timestamp: str                # ISO 8601; observation metadata, excluded from comparability digest
    sandbox_resource_limits: dict | None  # MVP: None; execution guardrails live in RunPlan/replay_canonical
    workspace_map: dict[str, str] | None  # task_id -> resolved git_commit (多 workspace 时)
```

当 Run 包含多个 task 且各 task 声明不同 workspace（不同 repo/ref），`workspace_map` 记录每个 task 解析后的 commit hash。单 workspace 时此字段为 None，`git_commit` 即为唯一起点。

**CellSnapshot 结构**（Cell 级 observed）：
```python
@dataclass
class CellSnapshot:
    git_commit: str | None        # actual commit at execution time
    git_dirty: bool
    setup_exit_code: int | None   # None if no setup_commands
    workspace_path: str           # actual path used
    timestamp: str                # ISO 8601
```

**SnapshotGateResult**：
```python
@dataclass
class SnapshotGateResult:
    status: Literal["pass", "warn", "fail"]
    mismatch_fields: list[str]    # e.g. ["git_commit", "setup_exit_code"]
    gate_version: str             # "1.0"
```

**Comparability Gate（MVP 行为）**：Execution Kernel 在每个 cell 执行后生成 CellSnapshot 并与 Run 级 SameStartSnapshot 对比。如果关键字段不一致，生成 `SnapshotGateResult(status="warn")`，Decision Layer 在报告中加入 comparability caveat；当 caveat 覆盖关键起点字段时，DecisionStatus 必须降级为 `not_comparable` 或 `inconclusive`。MVP 不阻塞执行（status 不会是 "fail"），但 gate result 必须持久化到 cell result 中。

---

### 4.6 Artifact / Trace Layer（L1）

**实现范围**：
- 每个 RunCell 的 stdout/stderr/output files 保存到 `.micro-eval/runs/{run_id}/cells/{cell_id}/`
- 每个 artifact 有稳定 ID（cell-scoped，保证跨 cell 唯一）
- 本地 artifact index：`manifest.json` 记录所有 artifact refs
- `output_summary` 是 artifact excerpt，不是完整 artifact
- UI 可从 result 链接到 artifact 原文
- Cost/latency 记录在 ExecutionResult 中，作为 evidence 可引用

**数据模型**：
```python
@dataclass
class ArtifactRef:
    artifact_id: str          # format: "{cell_id}::{kind}::{sha256_hex[:12]}"
    kind: Literal["stdout", "stderr", "file", "diff", "metadata"]
    path: Path                # relative to run dir
    size_bytes: int

@dataclass
class EvidenceItem:
    evidence_id: str
    kind: Literal["artifact", "validation", "score", "annotation"]
    source_kind: Literal["artifact_ref", "evaluation_id"]
    source_ref: str           # artifact_id (if source_kind=artifact_ref) or evaluation_id
    cell_id: str              # owning cell, for navigation
    status: Literal["passed", "failed", "error", "skipped"]
    severity: Literal["info", "warning", "critical"]
    summary: str | None       # excerpt, not full content

@dataclass
class CostMetric:
    currency: str             # "USD" | "tokens" | "unknown"
    amount: float | None      # None if not available
    source: str               # "adapter_env" | "trace" | "manual"
```

`artifact_id` 格式规范：`"{cell_id}::{kind}::{sha256_hex[:12]}"`。cell_id 前缀保证相同内容在不同 cell 中生成不同 artifact_id，解决相同 stdout 内容的定位歧义。

**Evidence 链路说明**：`EvaluationResult.evidence_refs` 存放的是 `evidence_id`，不能直接存 `artifact_id`。verdict 回溯链路为：`DecisionReport.verdict → evaluation_ids → EvaluationResult.evidence_refs → EvidenceItem.evidence_id → EvidenceItem.source_ref → ArtifactRef.artifact_id → 文件路径`。manifest.json 作为 artifact_id → path 的查找表。

**演进预留**：增量写入（cell 完成即写 artifact），为 Phase 2 event-sourcing 模式留空间。

---

### 4.7 Evaluation Layer（L0+L1）

**实现范围**：
- **L0 人工评分**：通过 Web UI 进行 pass/fail + 维度打分 + comment
- **L1 Deterministic validation**：expectations 自动校验（exit_code / contains / file_exists）
- 每个评分记录 rubric 版本、evaluator identity（human / validator）、evidence refs
- Validation 在 run 完成后自动执行；人工评分通过 UI 补充
- 评分结果持久化到 `.micro-eval/`（不再用 localStorage）

**Validation 类型（MVP 支持）**：
```yaml
expectations:
  - type: exit_code
    value: 0
  - type: contains
    target: stdout
    value: "expected string"
  - type: file_exists
    path: output/result.json
  - type: command
    argv: ["python", "validate.py"]  # safe argv, no shell interpolation
    cwd: "{output_dir}"              # workspace-relative, Kernel 注入
    timeout: 30
    exit_code: 0
```

**Validation command 安全约束**：`type: command` 必须使用 `argv` 列表形式（与 AgentInvocation 一致），禁止 shell 字符串。`{output_dir}` 由 Execution Kernel 在运行时替换为实际路径，不经过 shell 展开。

**EvaluationResult**：
```python
@dataclass
class EvaluationResult:
    evaluation_id: str
    run_cell_id: str
    evaluator: str                     # "validator" | "human" | future: "llm_judge"
    evaluator_meta: dict | None        # future: {"model": "claude-opus-4", "temperature": 0}
    rubric_hash: str | None            # rubric 子树的 sha256 hex[:16]
    scores: dict[str, float]           # dimension -> score
    pass_fail: bool | None
    comment: str | None
    evidence_refs: list[str]           # evidence_ids; each EvidenceItem points to artifact_id when needed
    timestamp: str                     # compact: "20260602T150000Z" (无冒号)
```

**持久化格式**：`evaluation.json` 为 `list[EvaluationResult]`（JSON 数组），每次评分 append 新条目，不覆盖已有评分。API route `POST .../evaluate` 语义为 append。

**`rubric_hash` 规范**：对 task YAML 中 `rubric:` 子树做 canonical JSON 序列化后取 sha256 hex[:16]。

**pass@k 与聚合指标**：MVP 默认 repetitions=1，此时 pass@k ≡ pass rate，无需额外计算。
当 repetitions>1 成为常态后，pass@k/pass^k 应升级为对比页默认指标——
其适用条件、binary-only 限制、denominator policy 见 Unicorn Design §5.7 权威定义，本文档不重述。
MVP 的 `EvaluationResult` 结构已能支撑 pass@k 计算（每个 rep 独立记录 pass_fail）。

**契约**：LLM judge 不在 MVP，但数据结构必须能容纳未来 `evaluator: "llm_judge"` + `judge_model: str`。

---

### 4.8 Secrets 管理（MVP 最小规格）

**实现范围**（对应 Unicorn Invariant #8 "Secrets are never evidence"）：
- **来源**：MVP 仅支持环境变量作为 secrets 来源（`MICRO_EVAL_SECRET_*` 前缀）
- **注入**：Configuration 中声明 `secrets: [ENV_VAR_NAME]`，Execution Kernel 将其注入 `AgentInvocation.env`
- **脱敏范围**：
  - stdout/stderr：持久化前执行 secret value redaction（替换为 `[REDACTED:ENV_VAR_NAME]`）
  - file/directory artifacts：对所有文本文件（<1MB）执行相同 redaction；二进制文件跳过但记录 warning
  - EvidenceItem.summary：不得包含原始 secret 值
- **不进 evidence**：任何 `EvidenceItem.summary` 和 `ArtifactRef` 引用的内容在持久化时已脱敏

**数据模型**：
```python
@dataclass
class SecretRedactor:
    patterns: dict[str, str]  # env_var_name -> actual_value (in memory only)

    def redact(self, text: str) -> str:
        for name, value in self.patterns.items():
            text = text.replace(value, f"[REDACTED:{name}]")
        return text
```

**流程**：
1. Run 开始 → 从 `os.environ` 读取所有 `MICRO_EVAL_SECRET_*` 变量，构建 `SecretRedactor`
2. AgentInvocation 构建 → 将 Configuration 声明的 secrets 注入 `env` dict
3. AdapterResult 返回 → `SecretRedactor.redact(stdout)` 和 `redact(stderr)` 后再写入文件
4. Manifest/Evidence 层 → 只引用 redacted artifacts

**MVP 不做**：keyring/vault 集成、per-tenant secrets、secrets rotation、secrets 审计日志。

---

### 4.9 Decision Layer（L0+L1）

**实现范围**：
- **ResultMatrix**：Tasks × Configurations 的表格展示
- 每个 cell 显示：pass/fail、scores、cost、latency、artifact link
- Repetitions 聚合：显示 N 次结果 + pass rate
- Evidence-linked summary：结论必须引用具体 cell 和 score
- **DecisionStatus taxonomy**（MVP 即引入）：`improved | regressed | mixed | inconclusive | not_comparable | needs_human_review`
- CLI `micro-eval report` 输出文本矩阵摘要
- Web UI 展示交互式 ResultMatrix

**Basic Honest Stats**（MVP 必须）：
- pass rate per configuration
- mean/median latency per configuration
- cost if present（从 adapter result 或 trace 提取）
- 低样本警告（repetitions < 3 时提示 "low confidence"）

**Must not bypass**：verdict 必须引用 EvaluationResult + EvidenceItem，不能只是主观结论。

**DecisionReport 预留结构**（GAP 7 stub，为 Phase 2 独立化做准备）：

run.json 中 verdict 相关字段组织为嵌套 `decision` 对象：
```python
# 嵌入 run.json 的 decision 子结构（Phase 2 拆为独立 decision.json）
decision: {
    "verdict": "improved",          # DecisionStatus taxonomy
    "confidence": "low",            # "high" | "medium" | "low"
    "evaluation_refs": [...],       # evaluation_ids 列表
    "evidence_refs": [...],         # evidence_ids 列表，用于支撑 verdict/caveats
    "caveats": ["low_sample"],      # SnapshotGateResult 等 caveat
    "aggregation": {                # GAP 5 stub: Phase 2 升级为独立 AggregationResult
        "pass_rate": {"claude-code-v2": 0.6, "cursor-agent": 0.8},
        "mean_latency_ms": {"claude-code-v2": 1200, "cursor-agent": 900},
        "cost": {"claude-code-v2": null, "cursor-agent": null}
    },
    "timestamp": "20260602T150000Z"
}
```

MVP 行为：`decision` 子结构在 `micro-eval report` 完成时写入 run.json。Phase 2 将其拆为独立 `decision.json` + 分配 `decision_report_id`，无需迁移旧数据（直接从 `run.json["decision"]` 提取）。

---

## 5. Stable IDs（MVP 必须实现）

| ID | 生成规则 | 示例 |
|----|----------|------|
| `task_id` | 用户声明的 slug | `code-review-basic` |
| `task_revision_id` | task YAML content hash（含引用 rubric 文件） | `sha256:a1b2c3...` |
| `agent_id` | 用户声明或 command hash 派生 | `claude-code-v2` |
| `configuration_id` | 用户声明的 id 字段（+ config_hash 伴随记录） | `claude-code-v2` |
| `run_id` | timestamp + random suffix | `20260602-143052-x7k` |
| `run_cell_id` | `{run_id}::{task_id}::{config_id}::rep-{n}` | `20260602-..::code-review::claude-v2::rep-1` |
| `artifact_id` | `{cell_id}::{kind}::{sha256_hex[:12]}` | `...::stdout::a1b2c3d4e5f6` |
| `evaluation_id` | `{run_cell_id}::{evaluator}::{compact_ts}` | `...::human::20260602T150000Z` |

**时间戳格式约束**：所有 ID 中嵌入的 timestamp 使用 compact 格式 `YYYYMMDDTHHmmssZ`（无冒号），避免与 `::` 分隔符冲突。

**`configuration_id` 稳定性说明**：MVP 允许用户直接声明 `id` 字段作为 `configuration_id`（简化上手体验）。但 run metadata / `replay_canonical` 中必须**同时记录** `config_content_hash`（agent+skill+env+params 的 canonical JSON digest）。如果用户修改了 configuration 内容但未更新 id，系统在 Run 开始时发出 warning："configuration content changed but id unchanged — results may not be comparable with previous runs." 这是对 Unicorn §4 "display name 不能作为稳定 ID" 的务实投影。

---

## 6. 数据持久化

所有 MVP 数据存储在项目根目录的 `.micro-eval/` 下：

```text
.micro-eval/
├── runs/
│   └── {run_id}/
│       ├── run.json              # RunPlan + metadata + intended SameStartSnapshot + replay_canonical
│       ├── manifest.json         # all artifact refs for this run
│       └── cells/
│           └── {cell_id}/
│               ├── result.json   # ExecutionResult + AdapterResult + CellSnapshot + SnapshotGateResult
│               ├── stdout.txt
│               ├── stderr.txt
│               ├── evaluation.json  # list[EvaluationResult] (append-only)
│               └── artifacts/       # output files
└── config/
    └── eval.yaml                 # copy of active config (not symlink, for portability)
```

格式：JSON（Pydantic 序列化），schema_version 字段标记版本。

**`replay_canonical` 子对象**（嵌入 run.json，支撑可复现性判断）：

run.json 中包含一个 `replay_canonical` 子对象，记录影响 replay identity 的全部输入。
Decision Layer 判断两次 run 是否可比较时，以此子对象为唯一依据。

```python
@dataclass
class ReplayCanonical:
    schema_version: str               # "1.0"
    micro_eval_version: str           # 工具版本（git describe 或 pyproject version）
    config_hash: str                  # eval.yaml content hash
    task_ids: list[str]               # 参与的 task_id 列表（有序）
    task_revision_digests: dict[str, str]  # task_id -> task_revision_id
    configuration_ids: list[str]      # 参与的 configuration_id 列表（有序）
    configuration_digests: dict[str, str]  # config_id -> config_content_hash
    environment_snapshot_digest: str  # SameStartSnapshot 的 canonical JSON digest（排除 timestamp / workspace_path 等观察元数据）
    max_concurrency: int
    retry_policy: dict | None         # max_attempts / retryable_exit_codes / backoff
    global_timeout_s: int
```

设计依据（参照 [[2026-06-02-pier-vs-unicorn-analysis]] §3.2 lock file 机制）：
- 不新建独立 `lock.json`——`run.json` 已是 run 的唯一事实源，
  `replay_canonical` 作为其子对象避免职责重叠。
- 排除 `created_at`、工具自身 git commit 等非 replay-affecting 字段。
- 两次 run 的 `replay_canonical` 相同 ⟹ Snapshot Gate 可直接给 `pass`。`timestamp`、实际临时 `workspace_path` 等观察元数据不得进入 digest，否则同配置重跑永远无法相同。
- Phase 2 如需独立 lock 文件（CI 场景），可从 `run.json["replay_canonical"]` 导出，无需迁移。

---

## 7. Web UI 范围（Next.js）

| 页面 | 功能 | 数据源 |
|------|------|--------|
| Run List | 所有 run，状态/时间/config 概览 | `.micro-eval/runs/*/run.json` |
| Run Detail / Matrix | Task × Configuration 矩阵 + scores + verdict | `manifest.json` + `result.json` |
| Cell Detail | 单个 cell 的 artifact viewer + 评分面板 | `cells/{id}/*` |
| Annotation Panel | 人工评分 + comment + rubric 维度 | 写回 `evaluation.json` |

**API Routes**（Next.js API routes 通过 RunStore 读取本地 `.micro-eval/` JSON；Route Handler 不直接拼路径读文件）：
- `GET /api/runs` → run 列表
- `GET /api/runs/[id]` → run detail + matrix
- `GET /api/runs/[id]/cells/[cellId]` → cell detail + artifacts
- `POST /api/runs/[id]/cells/[cellId]/evaluate` → 保存人工评分

**UI 不做**：配置编辑器、task 编辑器、实时执行进度、多用户协作。

---

## 8. 从 legacy v0.1.0 迁移

| 变更项 | legacy v0.1.0 | MVP target | 优先级 |
|--------|---------------|------------|:------:|
| Agent 调用 | `subprocess_shell` + 字符串 | `subprocess_exec` + argv 列表 | P0 |
| 数据模型 | baseline/candidate 二元 | Configuration 矩阵；MVP 默认 2-column pairwise | P0 |
| Workspace | WorkspaceManager 未接入 | git worktree 接入主流程 | P0 |
| Task 格式 | input_payload/expected_output | prompt/expectations/rubric | P0 |
| Artifact | output_summary 字段 | ArtifactRef + 文件存储 | P0 |
| 评分 | exact/contains 匹配 | validation + human scoring | P1 |
| Annotation | localStorage | 持久化 evaluation.json | P1 |
| Snapshot | 4 字段 | SameStartSnapshot + CellSnapshot 完整 | P0* |
| Schema | Pydantic/zod 不对齐 | 共享 schema，版本标记 | P2 |

**迁移依赖关系**：
- P0 依赖链：Configuration 模型 → Execution Kernel → Agent Adapter → Workspace/Snapshot → Artifact 基础存储。这是一条不可分割的链路。
- P0 进一步拆分为**两个可独立交付的里程碑**：
  - **P0-a（数据模型 + 执行骨架）**：新 schema 定义（Pydantic models）、Configuration 矩阵展开、AgentInvocation argv 调用、基础 stdout/stderr 保存。此阶段 CLI 可以 run 并产出 result.json，但无 workspace 隔离、无 snapshot。
  - **P0-b（workspace + snapshot + evidence 链路）**：git worktree 接入、SameStartSnapshot + CellSnapshot 记录、SnapshotGateResult 产出、manifest.json + artifact refs 完整。此阶段 verdict 可以从 `inconclusive` 升级为 `improved`/`regressed`。
- P1 项（evaluation.json 持久化、human scoring UI）依赖 P0-b 的 artifact 存储已就位。

**迁移原则**：P0-a 可独立交付一个"能跑但 verdict 全是 inconclusive"的版本；P0-b 补上 snapshot + evidence 后才能输出有意义的 verdict。这避免了 big-bang 问题，同时保证依赖链完整。

---

## 9. MVP 明确不含

- LLM-as-judge / DeepEval 自动评分
- Langfuse / OpenTelemetry **外部** trace 接入（注：内建 process-level trace provider 始终存在于 L1——wall clock、exit code、stderr、trace_id 注入——Langfuse 是 Phase 2 的外部 trace 后端升级）
- Docker / 容器沙箱
- Remote agent adapter
- 统计显著性检验 / 置信区间
- 跨 run 趋势分析
- RBAC / 多用户 / SSO
- Task 自动生成
- Plugin / extension system
- 在线服务部署（仅本地运行）
- Task package 目录格式（instruction.md + tests/ + environment/）——属 Asset Layer L2，见 Unicorn §5.1
- Network allowlist 执行——属 Environment Layer L2+，MVP 无网络隔离基础设施
- ATIF trajectory import——属 Artifact/Trace Layer L2，Phase 2 引入 file-based trace provider
- Deterministic subset 抽样（n_tasks / sample_seed）——属 Configuration Layer L2，MVP 用 include/exclude glob 即可
- Critique run（micro-eval critique）——属 Evaluation + Decision Layer L2，Phase 2 引入

---

## 10. 测试策略

| 层级 | 覆盖范围 | 工具 |
|------|----------|------|
| 单元测试 | Schema validation、ID 生成、snapshot 计算、argv 构建、secret redaction | pytest |
| 集成测试 | Run 全流程（mock agent = echo command）、artifact 写入、evaluation 读写 | pytest |
| E2E | CLI `micro-eval run` → 结果文件 → `micro-eval report` | pytest + subprocess |
| UI 测试 | API routes 返回正确 JSON、页面渲染 | vitest（待建立） |

**关键测试用例**（来自 Unicorn §5 Validation checklist）：
- Agent Adapter 拒绝 shell 字符串插值
- Workspace snapshot 包含 git commit（resolved hash, not branch ref）
- 单个 cell 超时不影响其他 cell
- Evaluation 必须关联 evidence refs
- ResultMatrix verdict 引用 evaluation

**"Must not bypass" 契约测试**（每条对应一个 pytest 断言）：

```python
# §4.3 Execution Kernel 不直接构造 command
def test_kernel_uses_adapter():
    """Kernel must call AgentAdapter, never subprocess directly."""
    # assert kernel delegates to adapter interface, not raw subprocess

# §4.4 AgentInvocation 必须通过 argv 列表
def test_adapter_rejects_shell_string():
    """AgentInvocation.argv must be list, shell=False enforced."""
    # assert create_subprocess_exec is used, never create_subprocess_shell

# §4.5 CellSnapshot 必须存在
def test_cell_result_has_snapshot():
    """Every result.json must contain cell_snapshot field."""
    # assert result["cell_snapshot"]["git_commit"] is not None

# §4.7 EvaluationResult 必须引用 evidence
def test_evaluation_has_evidence_refs():
    """EvaluationResult with pass_fail set must have non-empty evidence_refs."""
    # assert len(eval_result.evidence_refs) > 0

# §4.8 Verdict 必须引用 EvaluationResult
def test_verdict_requires_evaluation():
    """DecisionReport verdict != 'inconclusive' requires evaluation_ids."""
    # assert report.verdict in ("inconclusive", "not_comparable") or report.evaluation_refs

# §4.9 Secrets 不进 artifact
def test_secrets_redacted_from_artifacts():
    """stdout.txt/stderr.txt must not contain injected secret values."""
    # assert secret_value not in Path(stdout_path).read_text()
```

---

## 11. 升级路径

MVP 完成后，各模块只在内部升级 maturity level，不改变契约：

```text
Phase 2:
  Artifact/Trace L1 → L2    (Langfuse trace, event-sourcing, ATIF file-based trace import)
  Evaluation L1 → L2        (DeepEval custom metric, critique run as evidence)
  Decision L1 → L2          (richer stats, cost-quality tradeoff, viewer 下钻)
  Asset L1 → L2             (task package 目录格式, deterministic subset/sample_seed)
  Configuration L1 → L2     (n_tasks/sample_seed, matrix sweeps)

Phase 3:
  Environment L1 → L2       (Docker sandbox, resource limits, network allowlist enforcement)
  Agent Adapter L1 → L2     (OpenHands adapter, remote agent, network_allowlist 字段)
  Asset L2 → L3             (git-backed task library, shared collections)
```

Phase 2 具体能力说明（参照 [[2026-06-02-pier-vs-unicorn-analysis]]）：
- **ATIF file provider**：agent 将 trajectory.json 写到约定位置，micro-eval 作为 trace import 收集。
- **Critique run**：`micro-eval critique <run-id>` 产出解释性 evidence（失败原因分析、task 公平性评估），
  不替代 deterministic validation，不覆盖 verdict。
- **Task package**：instruction.md + task.yaml + tests/ 目录格式，服务 coding-agent benchmark 场景。
- **Viewer 下钻**：Run → Configuration/Task heatmap → Cell → Artifact → Trajectory → Validation。
- **Deterministic subset**：`n_tasks` + `sample_seed` 支持 benchmark 子集可复现与 smoke run。
