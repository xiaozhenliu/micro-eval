# 决策与注意事项

Run 完成后，micro-eval 会将所有任务结果综合为一份 **DecisionReport**。该报告回答核心问题：*候选配置是否优于基线？* 贯穿这一过程的关键理念是**保守设计**——micro-eval 宁愿给出 **inconclusive（无法判定）**，也不会制造一个虚假的赢家。

## 理念：诚实优先于自信

大多数评测工具会计算一个综合分数并宣布胜者。micro-eval 不这样做。每一个裁决都受到一组注意事项的约束，这些注意事项明确指出证据中的薄弱环节。一个决策的效力取决于支撑它的证据，系统让这条证据链可供追溯。

::: tip 保守的默认行为
`inconclusive` 和 `needs_human_review` 这样的裁决并不是失败——当证据不足以支持更强结论时，它们才是正确的答案。压制这些裁决只会制造虚假的信心。
:::

## DecisionReport 结构

`DecisionReport` 由 Python 的 `build_decision` 函数生成，并序列化到 `.micro-eval/runs/<run-id>/decision.json`。TypeScript 的 `recomputeDecision` 函数在 UI 中读取该结构。

```json
{
  "verdict": "mixed",
  "confidence": "medium",
  "evaluation_refs": [
    "runs/abc123/evals/task-refactor-eval.json",
    "runs/abc123/evals/task-docs-eval.json"
  ],
  "evidence_refs": [
    "runs/abc123/artifacts/task-refactor/stdout.txt",
    "runs/abc123/artifacts/task-docs/stdout.txt"
  ],
  "caveats": [
    {
      "kind": "low_sample",
      "detail": "configuration 'gpt-4o' ran only 2 repetitions (min_repetitions=5)",
      "affected_configs": ["gpt-4o"]
    }
  ],
  "aggregation": {
    "claude-3-5-sonnet": {
      "tasks_total": 4,
      "tasks_passed": 3,
      "tasks_failed": 1,
      "mean_score": 0.82,
      "p50_latency_ms": 4200,
      "p95_latency_ms": 8900
    },
    "gpt-4o": {
      "tasks_total": 4,
      "tasks_passed": 4,
      "tasks_failed": 0,
      "mean_score": 0.71,
      "p50_latency_ms": 3100,
      "p95_latency_ms": 6200
    }
  },
  "recommended_action": "Review task 'refactor-legacy' manually. claude-3-5-sonnet failed this task in all 3 repetitions while gpt-4o passed. Consider increasing repetitions to at least 5 before drawing conclusions."
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `verdict` | `DecisionStatus` | 整体对比结果 |
| `confidence` | `high` \| `medium` \| `low` | 随每条生效的注意事项降级 |
| `evaluation_refs` | `string[]` | 各任务 EvaluationResult 文件的路径 |
| `evidence_refs` | `string[]` | 支撑评测的制品文件路径 |
| `caveats` | `Caveat[]` | 证据中的薄弱环节——每条都会降低置信度 |
| `aggregation` | `Record<configId, Stats>` | 各配置的聚合指标 |
| `recommended_action` | `string` | 人类可读的下一步建议 |

## DecisionStatus 取值

`verdict` 字段为以下六种状态之一，每种状态反映不同的证据情况。

| 状态 | 含义 | 典型原因 |
|---|---|---|
| `improved` | 候选配置明显优于基线 | 候选在多数任务中胜出且重复次数充足 |
| `regressed` | 候选配置明显差于基线 | 候选在多数任务中落败 |
| `mixed` | 部分任务更好，部分更差 | 任务集中无主导赢家 |
| `inconclusive` | 证据不足以做出判断 | 重复次数少、评测缺失或信号相互矛盾 |
| `not_comparable` | 快照不匹配——对比无效 | 两次 Run 之间 workspace 状态、commit hash 或配置内容发生了偏离 |
| `needs_human_review` | 自动评测无法判定 | LLM judge 弃权或 expectations 未产生任何信号 |

::: warning `inconclusive` 不是 bug
如果 Run 返回 `inconclusive`，最常见的解决方法是在配置文件中增大 `repetitions`。统计噪声是真实存在的——尤其对于输出具有概率性的任务。
:::

## 注意事项系统

每条注意事项（caveat）是对比中一个有名称的结构性薄弱环节。注意事项会累积并降低 `confidence` 字段的值，出现在 DecisionReport 的 `caveats` 数组中。

### `snapshot_mismatch`

被对比的两次 Run 之间，workspace 状态、git commit 或沙箱配置存在差异。无论分数如何，这都会将裁决强制设为 `not_comparable`。

```yaml
caveats:
  - kind: snapshot_mismatch
    detail: "baseline used commit a3f9c12, candidate used commit 7b2d441"
    affected_configs: ["baseline", "candidate"]
```

### `low_sample`

收集到的重复次数少于配置的 `min_repetitions` 阈值。只要有任何配置受影响，置信度就会降至 `low`。

```yaml
caveats:
  - kind: low_sample
    detail: "configuration 'claude-3-5-sonnet' ran 2 of 5 required repetitions"
    affected_configs: ["claude-3-5-sonnet"]
```

### `missing_evidence`

结果矩阵中有一个或多个单元格没有附带评测结果。这通常发生在任务超时、子进程在产出输出前崩溃，或 LLM judge 不可用时。

```yaml
caveats:
  - kind: missing_evidence
    detail: "3 cells in the result matrix have no EvaluationResult"
    affected_cells: ["task-stress/gpt-4o/rep-2", "task-stress/gpt-4o/rep-3"]
```

### `config_drift`

某个配置 ID 在多次 Run 中被复用，但配置内容发生了变化（不同的模型、不同的超时、不同的 skill 路径）。这会导致历史趋势对比变得不可靠。

```yaml
caveats:
  - kind: config_drift
    detail: "configuration 'prod-agent' had model=claude-3-5-sonnet in run-001, model=claude-opus-4 in run-002"
    affected_configs: ["prod-agent"]
```

### `mixed_isolation`

同一次 Run 中的不同配置使用了不同的隔离级别（`logical`、`os_policy`、`container`、`vm`）。来自沙箱环境的结果可能无法与仅使用 logical worktree 的结果进行比较。

```yaml
caveats:
  - kind: mixed_isolation
    detail: "baseline used isolation=logical, candidate used isolation=os_policy"
    affected_configs: ["baseline", "candidate"]
```

::: tip 注意事项的严重程度
`snapshot_mismatch` 和 `config_drift` 是最严重的——它们影响的是可比性，而不仅仅是置信度。其他注意事项会降低置信度，但不会直接使对比失效。
:::

## 证据链追溯

DecisionReport 中的每个结论都有一条可遍历的证据链支撑：

```
DecisionReport
  └── aggregation (per_configuration stats)
        └── evaluation_refs[]
              └── EvaluationResult (per task × config × rep)
                    └── evidence_refs[]
                          └── EvidenceItem
                                └── ArtifactRef (stdout, stderr, file diff, trace)
```

Web UI（`micro-eval ui`）以交互方式渲染这条链。在对比视图中，点击 ResultMatrix 中的任意单元格可打开 EvaluationResult，进而可以导航到原始制品和 Langfuse trace（如已配置）。

通过 CLI 也可以直接检查这条链：

```bash
# 显示某次 Run 的顶层决策
micro-eval report --run-id abc123 --format json | jq '.decision'

# 列出某次 Run 的所有评测文件
ls .micro-eval/runs/abc123/evals/

# 查看特定单元格的制品
cat .micro-eval/runs/abc123/artifacts/task-refactor/claude-3-5-sonnet/rep-1/stdout.txt
```

## 跨语言一致性

决策逻辑在两处实现：

- **Python**：`micro_eval/evaluation/decision.py` — `build_decision(run_result: RunResult) -> DecisionReport`
- **TypeScript**：`ui/lib/decision.ts` — `recomputeDecision(runResult: RunResult): DecisionReport`

两个实现都通过 `tests/contract/test_decision_contract.py` 中的共享黄金 fixture 集进行契约测试。如果任何 fixture 的输出出现分歧，CI 将失败。

::: code-group

```python [Python — build_decision]
from micro_eval.evaluation.decision import build_decision
from micro_eval.store import load_run_result

run_result = load_run_result("abc123")
decision = build_decision(run_result)
print(decision.verdict)          # "mixed"
print(decision.confidence)       # "medium"
for caveat in decision.caveats:
    print(caveat.kind, caveat.detail)
```

```typescript [TypeScript — recomputeDecision]
import { recomputeDecision } from "@/lib/decision";
import { loadRunResult } from "@/lib/store";

const runResult = await loadRunResult("abc123");
const decision = recomputeDecision(runResult);
console.log(decision.verdict);        // "mixed"
console.log(decision.confidence);     // "medium"
decision.caveats.forEach((c) => {
  console.log(c.kind, c.detail);
});
```

:::

共享的 Pydantic schema（Python）和 zod schema（TypeScript）确保双方在字段名称、类型和允许的枚举值上保持一致。任何 schema 变更都必须在两处同步更新。

## not_comparable — 如何处理

::: danger `not_comparable` 阻断所有对比
如果裁决为 `not_comparable`，**所有分数、通过率和延迟对比均无效**。各配置并未在相同的环境中运行。请先修复快照问题，再重新运行。
:::

常见原因及修复方法：

| 原因 | 修复方法 |
|---|---|
| 不同次 Run 使用了不同的 git commit | 在两个配置中将 `workspace.git_repo.ref` 固定到相同的 commit hash |
| workspace 初始化命令发生变化 | 新建一次 Run——修改初始化命令后不要复用同一个 Run ID |
| 配置内容变更但 ID 被复用 | 创建新的配置 ID；不要修改已有的配置 |
| 使用了不同的隔离级别 | 在同一次 Run 的所有配置中设置相同的 `isolation` 级别 |

查看每个配置使用的快照：

```bash
micro-eval report --run-id abc123 --format json \
  | jq '.configurations[].same_start_snapshot'
```

如果各配置的 `same_start_snapshot` 哈希值不同，该 Run 在定义上即为 `not_comparable`。

## 置信度降级规则

置信度从 `high` 开始，按以下规则降级：

1. 存在任何 `snapshot_mismatch` 或 `config_drift` 注意事项 → 裁决强制设为 `not_comparable`，置信度设为 `low`
2. 存在任何 `low_sample` 注意事项 → 置信度降一级（high → medium，medium → low）
3. 存在任何 `missing_evidence` 注意事项 → 置信度降一级
4. 存在任何 `mixed_isolation` 注意事项 → 置信度降一级
5. 存在两条或两条以上非快照类注意事项 → 置信度设为 `low`

最终的 `confidence` 值反映所有生效注意事项的累积影响。

## 下一步

- [Workspace 隔离](/zh/guide/workspace-isolation) — 了解四种隔离级别以及 SameStartSnapshot 的计算方式
