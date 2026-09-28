# Decision & Caveats

::: tip Where you are in the decision loop
The **Decision** is the final output of the loop: a guarded conclusion linked to its evidence. See [Design System](./design-system#three-design-tensions) for why `inconclusive` is a valid answer.
:::

After a run completes, micro-eval writes a **DecisionReport** that asks whether the candidate improved on the baseline. Automatic comparisons use task-level validator pass rates and always report `confidence: low`; the verdict is not a statistical significance claim.

## Requirements for Automatic Comparison

A comparison needs exactly one configuration with `role: baseline` and one with `role: candidate`. Roles are recorded at planning time and are never inferred from list order. The run also preserves the evaluation contract used to make the decision, so later recomputation can use the recorded inputs.

Set `evaluation.decision_threshold` to a value in `(0, 1]` and use `required_evaluators: [validator]` for automatic comparison. For every task, both configurations must meet `min_repetitions` under the selected denominator policy and have auditable machine evidence. A null threshold, missing contract or roles, missing evidence, insufficient repetitions, or an incomplete run produces `inconclusive`. A contract requiring evaluators other than only `validator` produces `needs_human_review`.

`include_failed` counts completed error and timeout results in the denominator. `exclude_failed` keeps results with `passed` or `failed` status; it excludes execution errors and timeouts, not failed expectations.

## Task-Level Directions

For each task, micro-eval computes:

```text
delta = candidate_pass_rate - baseline_pass_rate
```

| Condition | Task direction |
|---|---|
| `delta >= decision_threshold` | `improved` |
| `delta <= -decision_threshold` | `regressed` |
| Otherwise | `unchanged` |

The overall verdict follows those task directions after the protection gates pass:

| Verdict | Meaning |
|---|---|
| `improved` | At least one task improves and none regress. |
| `regressed` | At least one task regresses and none improve. |
| `mixed` | Some tasks improve and others regress. |
| `inconclusive` | All tasks are unchanged, or the comparison requirements are unmet. |
| `not_comparable` | A cell snapshot gate is not `pass`, or baseline and candidate task sets differ. |
| `needs_human_review` | The evaluation contract requires a non-validator evaluator. |

A snapshot warning takes precedence over a cancelled-run conclusion. Otherwise, cancelled runs are `inconclusive` and summarize only the completed cells. Adding repetitions cannot repair a missing role, threshold, contract, or snapshot mismatch; inspect the recorded reason before rerunning.

## Reading the DecisionReport

The report is stored in `.micro-eval/runs/<run-id>/decision.json` and embedded in `run.json.decision`. This excerpt illustrates the comparison shape:

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

The `comparison.tasks` entries also carry cell, evaluation, evidence, artifact, and trace references. References are identifiers for recorded evidence, not arbitrary filesystem paths. `comparison` may be `null` when the gates prevent a comparison.

## Caveats and Confidence

`caveats` is a list of strings. Read it together with each cell's `snapshot_gate_result`; caveats do not apply a numeric confidence score or progressively lower a `high` starting confidence. Current automatic reports always use `low`.

| Recorded condition | Effect |
|---|---|
| Snapshot gate warning or mismatch | `not_comparable`; inspect the cell's mismatch fields and caveats. |
| Missing roles or persisted comparison contract | `inconclusive`; supply explicit roles and rerun with a complete contract. |
| `decision_threshold_not_set` | `inconclusive`; set a threshold before asking for an automatic winner. |
| `min_repetitions_not_met:<task>` | `inconclusive`; meet the required count on both sides of that task. |
| `machine_evidence_missing:<task>` | `inconclusive`; inspect validator/evidence records. |
| Fewer than three samples on either side | A low-sample caveat; comparison remains possible if `min_repetitions` is met. |
| `execution_failure_counted:<task>` | Errors or timeouts contributed to the denominator; inspect their artifacts. |
| Configuration drift or mixed run-level isolation | Retained as context; inspect the actual cell gates before making a direct comparison. |

OS policy and remote providers record their remaining limitations as snapshot caveats. Those warnings may prevent an automatic comparable verdict even when all task checks pass. Remote SDK contract tests do not establish live cloud isolation.

## Inspecting Evidence

The Web UI shows the verdict, task deltas, caveats, and result cells. Open a cell to inspect its evaluations and the referenced artifacts or traces. From the CLI, inspect the persisted record:

```bash
micro-eval report --run <run-id> --format json | jq '.decision'
micro-eval report --run <run-id> --format json | jq '.decision.comparison.tasks'
micro-eval report --run <run-id> --format json | jq '.results[].snapshot_gate_result'
```

When a run is `not_comparable`, its raw observations remain available, but they do not establish a controlled baseline/candidate improvement. Align workspace refs, inputs, setup, and effective isolation, inspect cleanup warnings, and rerun.

## Next Steps

- [Workspace Isolation](/guide/workspace-isolation) — provider boundaries and same-start evidence
- [Configuration](/guide/configuration#evaluation) — comparison settings
