# 决策与 Caveat

::: tip 在决策闭环中的位置
**Decision** 是闭环的最终输出：一份关联证据、受保护条件约束的结论。为什么 `inconclusive` 是有效答案，见[设计体系](./design-system#三大设计张力)。
:::

run 完成后，micro-eval 写入 **DecisionReport**，回答 candidate 是否优于 baseline。自动比较使用 task 级 validator 通过率，始终报告 `confidence: low`；verdict 不代表统计显著性结论。

## 自动比较的条件

比较要求恰好一个 `role: baseline` configuration 和一个 `role: candidate` configuration。角色在规划时记录，不会按列表顺序推断。run 同时保留用于决策的 evaluation contract，后续重算使用这些已记录的输入。

将 `evaluation.decision_threshold` 设为 `(0, 1]` 范围内的值，并使用 `required_evaluators: [validator]` 启用自动比较。每个 task 的两侧都必须按所选分母策略满足 `min_repetitions`，并具有可审计的机器证据。阈值为 null、缺少 contract 或角色、证据不足、重复次数不足、run 未完成时，结果为 `inconclusive`。合同要求的 evaluator 不仅有 `validator` 时，结果为 `needs_human_review`。

`include_failed` 将已完成的 error 和 timeout 结果计入分母。`exclude_failed` 保留状态为 `passed` 或 `failed` 的结果，排除的是执行错误和超时，不是 expectation 失败。

## Task 级方向

micro-eval 为每个 task 计算：

```text
delta = candidate_pass_rate - baseline_pass_rate
```

| 条件 | Task 方向 |
|---|---|
| `delta >= decision_threshold` | `improved` |
| `delta <= -decision_threshold` | `regressed` |
| 其他情况 | `unchanged` |

保护门禁通过后，总体 verdict 根据各 task 的方向确定：

| Verdict | 含义 |
|---|---|
| `improved` | 至少一个 task 改进，且没有 task 回退。 |
| `regressed` | 至少一个 task 回退，且没有 task 改进。 |
| `mixed` | 部分 task 改进，部分 task 回退。 |
| `inconclusive` | 所有 task 均未变化，或不满足比较条件。 |
| `not_comparable` | 某个 cell 的 snapshot gate 不是 `pass`，或 baseline 与 candidate 的 task 集不同。 |
| `needs_human_review` | evaluation contract 要求非 validator 的 evaluator。 |

snapshot 告警优先于取消 run 的结论。除此之外，取消的 run 为 `inconclusive`，仅汇总已完成的 cell。增加重复次数不能修复缺失的角色、阈值、contract 或 snapshot mismatch；重新运行前应检查已记录的原因。

## 阅读 DecisionReport

报告位于 `.micro-eval/runs/<run-id>/decision.json`，也嵌入 `run.json.decision`。以下节选展示 comparison 的结构：

```json
{
  "verdict": "improved",
  "confidence": "low",
  "evaluation_refs": ["eval-baseline-1", "eval-candidate-1"],
  "evidence_refs": ["evidence-baseline-1", "evidence-candidate-1"],
  "caveats": ["low sample size for repair: repetitions < 3"],
  "aggregation": {
    "per_configuration": {
      "baseline": {"n_cells": 2, "pass_rate": 0.5},
      "candidate": {"n_cells": 2, "pass_rate": 1.0}
    }
  },
  "comparison": {
    "baseline_configuration_id": "baseline",
    "candidate_configuration_id": "candidate",
    "decision_threshold": 0.1,
    "tasks": [{
      "task_id": "repair",
      "baseline_sample_count": 2,
      "candidate_sample_count": 2,
      "baseline_pass_rate": 0.5,
      "candidate_pass_rate": 1.0,
      "delta": 0.5,
      "direction": "improved"
    }]
  }
}
```

`comparison.tasks` 中还包含 cell、evaluation、evidence、artifact 和 trace 引用。引用是已记录证据的标识符，不是任意文件系统路径。门禁阻止比较时，`comparison` 可以为 `null`。

## Caveat 与置信度

`caveats` 是字符串列表，应结合每个 cell 的 `snapshot_gate_result` 阅读。caveat 不会计算数字置信分，也不会从 `high` 起点逐级降低置信度。当前自动报告始终使用 `low`。

| 记录的条件 | 影响 |
|---|---|
| Snapshot gate 告警或 mismatch | `not_comparable`；检查 cell 的 mismatch 字段与 caveat。 |
| 缺少角色或已持久化的 comparison contract | `inconclusive`；显式配置角色，并使用完整 contract 重新运行。 |
| `decision_threshold_not_set` | `inconclusive`；请求自动 winner 判断前先设置阈值。 |
| `min_repetitions_not_met:<task>` | `inconclusive`；满足该 task 两侧的重复次数要求。 |
| `machine_evidence_missing:<task>` | `inconclusive`；检查 validator/evidence 记录。 |
| 任一侧少于三个样本 | 记录 low-sample caveat；满足 `min_repetitions` 时仍可比较。 |
| `execution_failure_counted:<task>` | 错误或超时已计入分母；检查对应产物。 |
| Configuration drift 或 run 级混合隔离 | 作为上下文保留；直接比较前检查实际 cell gate。 |

OS 策略和远程 provider 会将仍存在的限制记录为 snapshot caveat。即使所有 task 检查通过，这些告警也可能阻止自动产生可比 verdict。远程 SDK contract 测试不能证明 live 云端隔离。

## 检查证据

Web UI 展示 verdict、task 差值、caveat 和结果 cell。打开 cell 可以检查 evaluation 及其引用的产物或 trace。在 CLI 中可以查看已持久化的记录：

```bash
micro-eval report --run <run-id> --format json | jq '.decision'
micro-eval report --run <run-id> --format json | jq '.decision.comparison.tasks'
micro-eval report --run <run-id> --format json | jq '.results[].snapshot_gate_result'
```

run 为 `not_comparable` 时，原始观察仍然可用，但不能据此建立受控的 baseline/candidate 改进结论。应对齐工作区 ref、输入、setup 和实际隔离级别，检查 cleanup 告警后再运行。

## 下一步

- [工作区隔离](/zh/guide/workspace-isolation) — provider 边界与同起点证据
- [配置](/zh/guide/configuration#evaluation) — 比较设置
