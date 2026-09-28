# 数据模型

micro-eval 将所有评测数据以 JSON 文件的形式存储在 `.micro-eval/runs/<run-id>/` 目录下。每个数据结构在 Python 侧用 Pydantic 定义，在 TypeScript 侧用 zod 镜像，确保 CLI 与 Web UI 之间共享同一套数据规范。

::: tip 文件目录结构
```
.micro-eval/
  runs/
    <run-id>/
      run.json          # RunRecord
      cells/
        <cell-id>.json  # CellResult
      artifacts/        # 二进制与文本 artifact
  index.sqlite          # 趋势索引（JSON 的只读投影）
```
:::

---

## RunRecord

一次 run 完成后写入的顶层记录，包含完整的配置矩阵、所有 cell 结果、可复现性快照及最终决策。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `string` | UUID v4，重试时保持不变。 |
| `project_name` | `string` | 来自 `eval.yaml` 的项目名称。 |
| `status` | `"planned" \| "running" \| "completed" \| "failed" \| "partial"` | 生命周期状态。`partial` 表示部分 cell 执行出错。 |
| `created_at` | `string` | ISO-8601 UTC 时间戳。 |
| `completed_at` | `string \| null` | run 完成或失败时设置。 |
| `failure_reason` | `string \| null` | run 失败或异常终止时的说明信息；成功时为 `null`。 |
| `output_dir` | `string` | `.micro-eval/runs/<run-id>/` 的绝对路径。 |
| `config_hash` | `string` | 所用 eval.yaml 的 SHA-256 哈希值。 |
| `tasks` | `TaskSpec[]` | 每个 task 定义的内联副本。 |
| `configurations` | `ConfigurationSpec[]` | 每个 configuration 定义的内联副本。 |
| `cells` | `CellSpec[]` | 所有 `(task, configuration, repetition)` 三元组的扁平列表。 |
| `results` | `CellResult[]` | 每个 cell 对应一条记录，`running` 状态下可能是部分列表。 |
| `execution_order` | `string[]` | 实际执行的 `cell_id` 有序列表。 |
| `execution_seed` | `integer` | 用于打乱执行顺序的随机种子。 |
| `same_start_snapshot` | `SameStartSnapshot` | 执行前捕获的可复现性信封。 |
| `replay_canonical` | `string` | 精确复现本次 run 的 CLI 命令。 |
| `artifacts` | `ArtifactRef[]` | run 级别的 artifact（如合并报告 PDF）。 |
| `evidence` | `EvidenceItem[]` | run 级别的证据条目。 |
| `traces` | `TraceRef[]` | run 级别的 Langfuse trace 引用。 |
| `evaluations` | `EvaluationResult[]` | 所有 cell 的全部评测结果。 |
| `decision` | `DecisionReport \| null` | 最终裁决，所有 cell 完成前为 `null`。 |
| `denominator_policy` | `"all_cells" \| "successful_cells"` | 计算 run 通过率时的分母策略。 |
| `owner` | `string \| null` | 发起本次 run 的成员。本地模式下为 `null`；服务器模式下由 worker 从任务的 `X-Micro-Eval-Member` 请求头中设置。 |
| `server_context` | `ServerContext \| null` | 强类型的团队服务器归属溯源信息（`workspace_id`、`owner`、`template_id`、`template_version`、`job_id`、`server_name`）；本地模式下为 `null`。 |

```json
{
  "id": "run-2026-0615-a3f9",
  "project_name": "pr-review-agent",
  "status": "completed",
  "created_at": "2026-06-15T09:00:00Z",
  "completed_at": "2026-06-15T09:04:22Z",
  "failure_reason": null,
  "output_dir": "/home/user/project/.micro-eval/runs/run-2026-0615-a3f9",
  "config_hash": "sha256:4e3d1a...",
  "tasks": ["..."],
  "configurations": ["..."],
  "cells": ["..."],
  "results": ["..."],
  "execution_order": ["cell-001", "cell-002", "cell-003"],
  "execution_seed": 42,
  "same_start_snapshot": { "...": "see SameStartSnapshot" },
  "replay_canonical": "micro-eval run --config eval.yaml --seed 42",
  "artifacts": [],
  "evidence": [],
  "traces": [],
  "evaluations": ["..."],
  "decision": { "...": "see DecisionReport" },
  "denominator_policy": "successful_cells",
  "owner": null,
  "server_context": null
}
```

---

## CellResult

单个 cell 是一次 `(task, configuration, repetition)` 执行。CellResult 存储该次执行的原始输出、评分及元数据。

| 字段 | 类型 | 说明 |
|---|---|---|
| `cell_id` | `string` | 由 `task_id + config_id + repetition` 派生的稳定 ID。 |
| `run_id` | `string` | 父级 `RunRecord.id`。 |
| `task_id` | `string` | 来自 `eval.yaml` 的 task 标识符。 |
| `configuration_id` | `string` | 来自 `eval.yaml` 的 configuration 标识符。 |
| `configuration_name` | `string` | 人类可读的 configuration 标签。 |
| `repetition` | `integer` | 从 0 开始的重复编号。 |
| `status` | `"pass" \| "fail" \| "error" \| "timeout"` | 执行结果。 |
| `score` | `float \| null` | [0, 1] 范围内的综合得分。 |
| `pass_fail` | `boolean \| null` | 所有评测器运行后的确定性通过/失败结论。 |
| `output_summary` | `string \| null` | agent 输出的前 500 个字符。 |
| `stdout_summary` | `string \| null` | stdout 的前 500 个字符。 |
| `stderr_summary` | `string \| null` | stderr 的前 500 个字符。 |
| `exit_code` | `integer \| null` | 进程退出码。 |
| `latency_s` | `float` | 实际执行耗时（秒）。 |
| `failure_mode` | `string \| null` | `status != "pass"` 时的分类失败标签。 |
| `stdout_truncated` | `boolean` | stdout 是否被截断为摘要。 |
| `stderr_truncated` | `boolean` | stderr 是否被截断为摘要。 |
| `output_truncated` | `boolean` | agent 输出是否被截断。 |
| `artifact_refs` | `ArtifactRef[]` | cell 范围的 artifact（diff、输出文件等）。 |
| `evidence_refs` | `string[]` | 与本 cell 关联的 `EvidenceItem` ID 列表。 |
| `evaluation_refs` | `string[]` | 本 cell 的 `EvaluationResult` ID 列表。 |
| `trace_refs` | `TraceRef[]` | 本 cell 的 Langfuse trace 链接。 |
| `cell_snapshot` | `object \| null` | 执行后采集的时间点 workspace 快照。 |
| `snapshot_gate_result` | `"pass" \| "fail" \| "skipped"` | 本 cell 是否通过快照可比性门控。 |

```json
{
  "cell_id": "cell-run-2026-0615-a3f9-task-fix-bug-config-gpt4o-rep0",
  "run_id": "run-2026-0615-a3f9",
  "task_id": "fix-bug",
  "configuration_id": "gpt4o",
  "configuration_name": "GPT-4o baseline",
  "repetition": 0,
  "status": "pass",
  "score": 0.85,
  "pass_fail": true,
  "output_summary": "Fixed the off-by-one error in line 42 of parser.py...",
  "stdout_summary": "Running tests...\n✓ 42 passed",
  "stderr_summary": null,
  "exit_code": 0,
  "latency_s": 18.4,
  "failure_mode": null,
  "stdout_truncated": false,
  "stderr_truncated": false,
  "output_truncated": false,
  "artifact_refs": [
    {
      "artifact_id": "art-001",
      "kind": "diff",
      "path": "artifacts/cell-fix-bug-gpt4o-rep0.diff",
      "sha256": "sha256:9b1c2a...",
      "size_bytes": 1024,
      "media_type": "text/plain",
      "redacted": false,
      "warning": null
    }
  ],
  "evidence_refs": ["ev-001"],
  "evaluation_refs": ["eval-001"],
  "trace_refs": [],
  "cell_snapshot": null,
  "snapshot_gate_result": "pass"
}
```

---

## DecisionReport

所有 cell 完成后计算出的最终裁决，汇总各 configuration 的统计数据，并附带置信度给出 `DecisionStatus`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `decision_report_id` | `string` | UUID。 |
| `verdict` | `DecisionStatus` | 六种状态之一（见下文）。 |
| `confidence` | `"high" \| "medium" \| "low"` | 对裁决的置信度。 |
| `evaluation_refs` | `string[]` | 支撑裁决的评测 ID 列表。 |
| `evidence_refs` | `string[]` | 支撑裁决的证据 ID 列表。 |
| `caveats` | `string[]` | 人类可读的注意事项（如"仅 2 次重复"）。 |
| `aggregation` | `AggregationResult` | 每个 configuration 的 `ConfigurationStats`。 |
| `timestamp` | `string` | 报告生成时的 ISO-8601 UTC 时间戳。 |
| `recommended_action` | `string \| null` | 可选的自由文本建议。 |

**DecisionStatus 取值：**

| 状态 | 含义 |
|---|---|
| `improved` | 挑战者 configuration 在统计上更优。 |
| `regressed` | 挑战者 configuration 在统计上更差。 |
| `mixed` | 部分 task 有提升，部分有退化。 |
| `inconclusive` | 结果在噪声范围内，无明确胜者。 |
| `not_comparable` | 各 cell 的起始条件不同，不可比较。 |
| `needs_human_review` | LLM judge 或自动评测器无法得出裁决。 |

```json
{
  "decision_report_id": "dr-2026-0615-001",
  "verdict": "improved",
  "confidence": "high",
  "evaluation_refs": ["eval-001", "eval-002", "eval-003"],
  "evidence_refs": ["ev-001"],
  "caveats": ["Only 3 repetitions per configuration"],
  "aggregation": {
    "configurations": {
      "gpt4o": { "pass_rate": 0.67, "mean_latency_ms": 18400 },
      "claude-sonnet": { "pass_rate": 0.89, "mean_latency_ms": 12200 }
    }
  },
  "timestamp": "2026-06-15T09:04:30Z",
  "recommended_action": "Adopt claude-sonnet configuration for production."
}
```

---

## ConfigurationStats

一次 run 中某个 configuration 跨所有 task 和重复次数的汇总统计，用于 `DecisionReport.aggregation` 内部。

| 字段 | 类型 | 说明 |
|---|---|---|
| `n_cells` | `integer` | 该 configuration 的总 cell 数。 |
| `n_successful` | `integer` | 未出错且未超时的 cell 数。 |
| `pass_rate` | `float` | 分母 cell 中通过的比例。 |
| `pass_at_k` | `float \| null` | pass@k：k 次重复中至少有一次通过的概率。 |
| `pass_hat_k` | `float \| null` | pass^k：k 次重复中预期通过的比例。 |
| `mean_latency_ms` | `float \| null` | 成功 cell 的平均实际耗时（毫秒）。 |
| `median_latency_ms` | `float \| null` | 实际耗时中位数（毫秒）。 |
| `total_cost` | `CostMetric` | 该 configuration 所有 cell 的成本总和。 |
| `denominator_policy` | `"all_cells" \| "successful_cells"` | 计入 `pass_rate` 的 cell 范围。 |
| `caveats` | `string[]` | 如 `["2 cells timed out"]`。 |

```json
{
  "n_cells": 9,
  "n_successful": 9,
  "pass_rate": 0.889,
  "pass_at_k": 0.999,
  "pass_hat_k": 0.889,
  "mean_latency_ms": 12200,
  "median_latency_ms": 11800,
  "total_cost": {
    "amount": 0.142,
    "currency": "USD",
    "source": "langfuse"
  },
  "denominator_policy": "successful_cells",
  "caveats": []
}
```

---

## EvaluationResult

针对单个 cell 的一次评测过程。每个 cell 可运行多个评测器（确定性验证器、LLM judge、人工标注），每个评测器各自产生一条 `EvaluationResult`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `evaluation_id` | `string` | UUID。 |
| `cell_id` | `string` | 本次评测所覆盖的 cell。 |
| `evaluator_type` | `"deterministic" \| "llm_judge" \| "human"` | 评测器类别。 |
| `evaluator` | `string` | 评测器名称或模型（如 `"exit_code_validator"`、`"claude-3-7-sonnet"`）。 |
| `pass_fail` | `"pass" \| "fail" \| null` | 二元裁决，仅有分数时为 `null`。 |
| `score` | `float \| null` | [0, 1] 范围内的数值评分。 |
| `scores` | `object` | 各维度评分（如 `{"correctness": 0.9, "style": 0.7}`）。 |
| `evaluator_meta` | `object` | 评测器特定元数据（模型参数、token 用量等）。 |
| `rubric_hash` | `string \| null` | LLM judge 或人工评测所用评分标准的 SHA-256 哈希值。 |
| `comment` | `string \| null` | 评测器的自由文本推理说明。 |
| `evidence_refs` | `string[]` | 支撑本次评测的 `EvidenceItem` ID 列表。 |
| `created_at` | `string` | ISO-8601 UTC 时间戳。 |

::: tip 评测流水线
micro-eval 按顺序运行各评测器：**确定性验证器 → LLM judge → 人工标注**。每个阶段均为可选。确定性检查失败的 cell 不会进入 LLM judge 阶段，除非显式配置。
:::

```json
{
  "evaluation_id": "eval-001",
  "cell_id": "cell-run-2026-0615-a3f9-task-fix-bug-config-gpt4o-rep0",
  "evaluator_type": "deterministic",
  "evaluator": "exit_code_validator",
  "pass_fail": "pass",
  "score": 1.0,
  "scores": {},
  "evaluator_meta": { "expected_exit_code": 0, "actual_exit_code": 0 },
  "rubric_hash": null,
  "comment": null,
  "evidence_refs": [],
  "created_at": "2026-06-15T09:02:10Z"
}
```

```json
{
  "evaluation_id": "eval-002",
  "cell_id": "cell-run-2026-0615-a3f9-task-fix-bug-config-gpt4o-rep0",
  "evaluator_type": "llm_judge",
  "evaluator": "claude-sonnet-4-5",
  "pass_fail": "pass",
  "score": 0.85,
  "scores": {
    "correctness": 0.9,
    "code_quality": 0.8,
    "test_coverage": 0.85
  },
  "evaluator_meta": {
    "input_tokens": 1200,
    "output_tokens": 340,
    "model": "claude-sonnet-4-5"
  },
  "rubric_hash": "sha256:7f3b4c...",
  "comment": "The fix correctly addresses the off-by-one error. Tests pass. Minor style nit on variable naming.",
  "evidence_refs": ["ev-001"],
  "created_at": "2026-06-15T09:02:45Z"
}
```

---

## ArtifactRef

指向 agent 或评测流水线生成的文件 artifact 的指针，实际文件存储在 `.micro-eval/runs/<run-id>/artifacts/` 目录下。

| 字段 | 类型 | 说明 |
|---|---|---|
| `artifact_id` | `string` | UUID。 |
| `kind` | `string` | 语义类型：`"diff"`、`"output_file"`、`"log"`、`"report"`、`"screenshot"` 等。 |
| `path` | `string` | 相对于 `output_dir` 的路径。 |
| `sha256` | `string` | 用于完整性验证的内容哈希值。 |
| `size_bytes` | `integer` | 文件大小。 |
| `media_type` | `string` | MIME 类型（如 `"text/plain"`、`"application/json"`）。 |
| `redacted` | `boolean` | 若在存储前已清除敏感值则为 `true`。 |
| `warning` | `string \| null` | 当脱敏不完整或文件存在异常时设置。 |

::: warning 敏感信息脱敏
内容匹配 `MICRO_EVAL_SECRET_*` 环境变量模式的 artifact 在写入磁盘前会自动脱敏。`redacted` 标志将被设为 `true`，`warning` 字段将包含脱敏摘要。
:::

```json
{
  "artifact_id": "art-001",
  "kind": "diff",
  "path": "artifacts/cell-fix-bug-gpt4o-rep0.diff",
  "sha256": "sha256:9b1c2a3d4e5f...",
  "size_bytes": 1024,
  "media_type": "text/plain",
  "redacted": false,
  "warning": null
}
```

---

## TraceRef

指向外部 Langfuse trace 的链接。trace 为可选功能，仅在配置了 Langfuse 时才会写入。

| 字段 | 类型 | 说明 |
|---|---|---|
| `trace_id` | `string` | Langfuse trace ID（Langfuse 不可用时为本地 UUID）。 |
| `provider` | `"langfuse" \| "local"` | 完整 trace 的存储位置。 |
| `external_url` | `string \| null` | Langfuse trace 查看器的直接 URL。 |
| `cost` | `CostMetric` | 归因于本 trace 的成本。 |
| `summary` | `string \| null` | 被追踪内容的简短描述。 |

```json
{
  "trace_id": "lf-trace-abc123",
  "provider": "langfuse",
  "external_url": "https://cloud.langfuse.com/project/my-project/traces/lf-trace-abc123",
  "cost": {
    "amount": 0.018,
    "currency": "USD",
    "source": "langfuse"
  },
  "summary": "Agent call for task fix-bug, configuration gpt4o, rep 0"
}
```

---

## EvidenceItem

支撑评测裁决的结构化证据条目，将原始观测数据（stdout、diff、测试结果）与评测层关联起来。

| 字段 | 类型 | 说明 |
|---|---|---|
| `evidence_id` | `string` | UUID。 |
| `kind` | `string` | `"test_result"`、`"diff"`、`"log_excerpt"`、`"assertion"`、`"human_note"` 等。 |
| `summary` | `string` | 一句话描述本条证据的内容。 |
| `source_kind` | `"stdout" \| "stderr" \| "artifact" \| "evaluator" \| "human"` | 证据来源。 |
| `source_ref` | `string \| null` | 来源对象的 ID（如 `artifact_id` 或 `evaluation_id`）。 |
| `cell_id` | `string \| null` | 本条证据所属的 cell，run 级别证据为 `null`。 |
| `status` | `"pass" \| "fail" \| "info"` | 证据是正面、负面还是中性的。 |
| `severity` | `"critical" \| "major" \| "minor" \| "info"` | 对裁决汇总的影响权重。 |
| `artifact_refs` | `ArtifactRef[]` | 支撑性 artifact 文件。 |
| `metadata` | `object` | 自由格式键值数据（如 `{"test_name": "test_parser"}`）。 |

```json
{
  "evidence_id": "ev-001",
  "kind": "test_result",
  "summary": "All 42 unit tests passed after the agent's change.",
  "source_kind": "stdout",
  "source_ref": null,
  "cell_id": "cell-run-2026-0615-a3f9-task-fix-bug-config-gpt4o-rep0",
  "status": "pass",
  "severity": "major",
  "artifact_refs": [],
  "metadata": {
    "test_suite": "pytest",
    "n_passed": 42,
    "n_failed": 0
  }
}
```

---

## SameStartSnapshot

在执行开始前捕获，用于验证 run 中所有 cell 均以相同条件启动。未通过快照门控的 cell 将被标记为 `not_comparable`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `workspace_type` | `"blank" \| "files" \| "git_repo"` | workspace 的初始化方式。 |
| `git_commit` | `string \| null` | 快照时的 HEAD commit SHA，非 git workspace 为 `null`。 |
| `dirty` | `boolean` | 工作树是否存在未提交的改动。 |
| `config_hash` | `string` | 所用 eval.yaml 的 SHA-256 哈希值。 |
| `configuration_digests` | `object` | 每个 configuration 解析后参数的摘要映射：`config_id → digest`。 |
| `task_revisions` | `object` | 每个 task 定义的内容哈希映射：`task_id → content_hash`。 |
| `python_version` | `string` | Python 版本字符串（如 `"3.11.9"`）。 |
| `setup_commands_digest` | `string \| null` | 所有 setup 命令拼接后的哈希值。 |
| `guardrails_digest` | `string \| null` | 当前有效 guardrail 策略文件的哈希值。 |
| `sandbox_policy` | `string` | 隔离级别：`"logical"`、`"os_policy"`、`"container"` 或 `"vm"`。 |
| `network_policy` | `string` | 网络访问策略：`"none"`、`"localhost"` 或 `"unrestricted"`。 |
| `toolchain_fingerprint` | `object` | 关键工具版本（如 `{"uv": "0.4.1", "node": "22.0.0"}`）。 |
| `fixture_digests` | `object` | 多源 fixture 的路径到 SHA-256 映射。 |
| `timestamp` | `string` | ISO-8601 UTC 时间戳。 |
| `caveats` | `string[]` | 快照警告（如 `["dirty working tree"]`）。 |

::: warning 工作树存在未提交改动
若 `dirty: true`，run 仍会执行，但 `DecisionReport.verdict` 可能被设为 `not_comparable`，因为 workspace 状态无法精确复现。对可复现性要求较高的评测，请在运行前提交或暂存所有改动。
:::

::: tip Sandbox 策略
| 策略 | 机制 | 适用场景 |
|---|---|---|
| `logical` | git worktree | 默认。速度快，无 OS 级隔离。 |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | 在不使用容器的情况下限制文件系统与网络。 |
| `container` | Docker / OCI | 完整容器隔离。 |
| `vm` | E2B / Modal | 远程云端执行，隔离最强。 |

若请求的策略不可用，将回退到 `logical` 并添加一条 caveat。
:::

```json
{
  "workspace_type": "git_repo",
  "git_commit": "4fd51c1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e",
  "dirty": false,
  "config_hash": "sha256:4e3d1a...",
  "configuration_digests": {
    "gpt4o": "sha256:a1b2c3...",
    "claude-sonnet": "sha256:d4e5f6..."
  },
  "task_revisions": {
    "fix-bug": "sha256:7890ab...",
    "add-test": "sha256:cdef01..."
  },
  "python_version": "3.11.9",
  "setup_commands_digest": "sha256:23456c...",
  "guardrails_digest": null,
  "sandbox_policy": "os_policy",
  "network_policy": "none",
  "toolchain_fingerprint": {
    "uv": "0.4.1",
    "node": "22.0.0",
    "git": "2.45.0"
  },
  "fixture_digests": {
    "fixtures/seed-data.sql": "sha256:fedcba..."
  },
  "timestamp": "2026-06-15T09:00:00Z",
  "caveats": []
}
```

---

## CostMetric

附加到 trace 或 configuration 汇总统计上的货币成本数据。当成本数据不可用时（如未集成 Langfuse），`amount` 可为 `null`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `amount` | `float \| null` | 成本金额，`null` 表示不可用。 |
| `currency` | `string` | ISO-4217 货币代码，默认为 `"USD"`。 |
| `source` | `string` | 成本数据来源：`"langfuse"`、`"estimated"` 或 `"manual"`。 |

```json
{
  "amount": 0.018,
  "currency": "USD",
  "source": "langfuse"
}
```

::: tip 成本数据可用性
成本数据仅在通过 `LANGFUSE_PUBLIC_KEY` 和 `LANGFUSE_SECRET_KEY` 配置 Langfuse 后才会填充。缺少这些变量时，micro-eval 会将 `amount` 设为 `null`、`source` 设为 `"unavailable"`，而不会导致 run 失败。
:::

---

## Schema 校验

完整的 Pydantic schema 位于 `micro_eval/schema/` 目录，zod 镜像位于 `ui/src/lib/schema/` 目录，两者均从同一套规范字段定义生成。

::: code-group

```python [Python (Pydantic)]
from micro_eval.schema import RunRecord, CellResult, DecisionReport

# 校验从磁盘加载的 run.json
with open(".micro-eval/runs/run-001/run.json") as f:
    data = json.load(f)

record = RunRecord.model_validate(data)
print(record.decision.verdict)  # "improved"
```

```typescript [TypeScript (zod)]
import { RunRecord } from "@/lib/schema/run";

// 用于读取 run.json 的 Next.js API route
const raw = JSON.parse(fs.readFileSync(runJsonPath, "utf-8"));
const record = RunRecord.parse(raw);
console.log(record.decision?.verdict); // "improved"
```

:::

---

## 服务器模式数据结构

以下结构仅在运行 `micro-eval serve` 时存在，存储在 `<data-root>/` 目录下，与 workspace run 数据并列。

### WorkspaceMeta

存储路径：`<data-root>/workspaces/<workspace-id>/workspace.json`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `workspace_id` | `string` | UUID v4。 |
| `name` | `string` | 人类可读的 workspace 名称。 |
| `owner` | `string` | workspace 创建者的成员标识。 |
| `template_id` | `string \| null` | 初始化 workspace 时使用的模板 ID。从头创建时为 `null`。 |
| `template_version` | `string \| null` | 创建时使用的模板版本。 |
| `created_at` | `string` | ISO-8601 UTC 时间戳。 |
| `last_run_at` | `string \| null` | 最近一次 run 的时间戳。尚未有 run 时为 `null`。 |
| `run_count` | `integer` | 该 workspace 中已完成的 run 总数。 |
| `description` | `string \| null` | 可选的自由文本描述。 |
| `status` | `"active" \| "archived"` | 生命周期状态。已归档的 workspace 在默认列表视图中不显示。 |

```json
{
  "workspace_id": "ws-2026-0619-a1b2",
  "name": "PR Review Agent v2",
  "owner": "alice",
  "template_id": "claude-code-v1",
  "template_version": "3",
  "created_at": "2026-06-19T09:00:00Z",
  "last_run_at": "2026-06-19T11:30:00Z",
  "run_count": 4,
  "description": "评测更新后的 PR review skill。",
  "status": "active"
}
```

---

### TemplateMeta

存储路径：`<data-root>/templates/<template-id>/template.json`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `template_id` | `string` | 唯一 slug（如 `"claude-code-v1"`）。 |
| `name` | `string` | 人类可读的模板名称。 |
| `description` | `string \| null` | 可选描述。 |
| `version` | `string` | 单调递增的版本字符串，每次 `template update` 后自增。 |
| `created_at` | `string` | ISO-8601 UTC 时间戳。 |
| `updated_at` | `string` | 最近一次 `template update` 的 ISO-8601 UTC 时间戳。 |
| `author` | `string \| null` | 创建或最后更新模板的成员。 |
| `tags` | `string[]` | 用于筛选的可选标签（如 `["coding", "review"]`）。 |
| `includes` | `string[]` | 模板中打包的文件路径列表，相对于模板根目录。 |

```json
{
  "template_id": "claude-code-v1",
  "name": "Claude Code v1",
  "description": "Claude Code agent 任务的基线评测套件。",
  "version": "3",
  "created_at": "2026-06-10T08:00:00Z",
  "updated_at": "2026-06-18T14:22:00Z",
  "author": "alice",
  "tags": ["coding", "review"],
  "includes": ["eval.yaml", "tasks/fix-bug.yaml", "tasks/refactor.yaml"]
}
```

---

### Job 记录

存储在 `<data-root>/queue.db` SQLite 数据库的 `jobs` 表中。

| 列名 | 类型 | 说明 |
|------|------|------|
| `job_id` | `TEXT` | UUID v4，主键。 |
| `workspace_id` | `TEXT` | 外键——拥有该任务的 workspace。 |
| `owner` | `TEXT` | 入队时 `X-Micro-Eval-Member` 请求头的值。 |
| `plan_json` | `TEXT` | 序列化的 `RunPlan` JSON，由 workspace `eval.yaml` 加上覆盖字段构建。 |
| `status` | `TEXT` | 任务生命周期状态（见下文）。 |
| `enqueued_at` | `TEXT` | ISO-8601 UTC 时间戳。 |
| `started_at` | `TEXT \| null` | worker 取出任务时设置。 |
| `finished_at` | `TEXT \| null` | 任务进入终态时设置。 |
| `run_id` | `TEXT \| null` | 为该任务创建的 `RunRecord.id`，执行开始前为 `null`。 |
| `error` | `TEXT \| null` | `status = "failed"` 时的错误信息。 |
| `progress` | `TEXT \| null` | worker 在执行过程中更新的 JSON 进度快照（如 `{"done": 3, "total": 12}`）。 |
| `cancel_requested_at` | `TEXT \| null` | 任务运行时收到取消请求时设置。 |
| `cancelled_by` | `TEXT \| null` | 请求取消的成员。 |

**状态值及转换：**

```
queued → running → done
                 → failed
                 → cancelled
```

| 状态 | 含义 |
|------|------|
| `queued` | 等待队列中，尚未被 worker 取出。 |
| `running` | worker 正在执行各 cell。 |
| `done` | 所有 cell 已成功完成（部分 cell 得分可能为 0）。 |
| `failed` | run 因不可恢复的错误而中止。 |
| `cancelled` | 通过 `micro-eval queue cancel` 或 UI 请求取消。 |
