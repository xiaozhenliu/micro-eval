# Decision & Caveats

::: tip Where you are in the decision loop
The **Decision** is the final output of the loop — a guarded, evidence-backed conclusion.
See [Design System](./design-system#three-design-tensions) for why "inconclusive" is a valid answer.
:::

After a run completes, micro-eval synthesizes all task results into a single **DecisionReport**. This report answers the core question: *does the candidate configuration outperform the baseline?* The key philosophy guiding this process is conservative by design — micro-eval would rather say **inconclusive** than manufacture a false winner.

## Philosophy: Honest Over Confident

Most evaluation tools compute an aggregate score and declare a winner. micro-eval does not. Every verdict is guarded by a set of caveats that explicitly name the weaknesses in the evidence. A decision is only as strong as the evidence supporting it, and the system makes that chain of evidence navigable.

::: tip Conservative Defaults
Verdicts like `inconclusive` and `needs_human_review` are not failures — they are correct answers when the evidence does not justify a stronger claim. Suppressing them would create false confidence.
:::

## DecisionReport Structure

The `DecisionReport` is produced by the Python `build_decision` function and serialized to `.micro-eval/runs/<run-id>/decision.json`. The TypeScript `recomputeDecision` function reads this structure in the UI.

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

| Field | Type | Description |
|---|---|---|
| `verdict` | `DecisionStatus` | The overall comparison outcome |
| `confidence` | `high` \| `medium` \| `low` | Degrades with each active caveat |
| `evaluation_refs` | `string[]` | Paths to per-task EvaluationResult files |
| `evidence_refs` | `string[]` | Paths to artifact files backing the evaluations |
| `caveats` | `Caveat[]` | Weaknesses in the evidence — each one reduces confidence |
| `aggregation` | `Record<configId, Stats>` | Per-configuration aggregate metrics |
| `recommended_action` | `string` | Human-readable next step |

## DecisionStatus Values

The `verdict` field is one of six statuses. Each reflects a different evidential situation.

| Status | Meaning | Typical Cause |
|---|---|---|
| `improved` | Candidate clearly outperforms baseline | Candidate wins on majority of tasks with sufficient repetitions |
| `regressed` | Candidate clearly worse than baseline | Candidate loses on majority of tasks |
| `mixed` | Better on some tasks, worse on others | No dominant winner across task set |
| `inconclusive` | Evidence insufficient to decide | Low repetitions, missing evaluations, or contradictory signals |
| `not_comparable` | Snapshots don't match — comparison invalid | Workspace state, commit hash, or config content diverged between runs |
| `needs_human_review` | Automated evaluation cannot determine | LLM judge abstained or expectations produced no signal |

::: warning `inconclusive` is not a bug
If a run returns `inconclusive`, the most common fix is to increase `repetitions` in your configuration file. Statistical noise is real — especially for tasks with probabilistic outputs.
:::

## The Caveat System

Each caveat is a named structural weakness in the comparison. Caveats accumulate and degrade the `confidence` field. They appear in the `caveats` array of the DecisionReport.

### `snapshot_mismatch`

The workspace state, git commit, or sandbox configuration differs between the runs being compared. This forces the verdict to `not_comparable` regardless of scores.

```yaml
caveats:
  - kind: snapshot_mismatch
    detail: "baseline used commit a3f9c12, candidate used commit 7b2d441"
    affected_configs: ["baseline", "candidate"]
```

### `low_sample`

Fewer repetitions were collected than the configured `min_repetitions` threshold. Confidence drops to `low` if any configuration is affected.

```yaml
caveats:
  - kind: low_sample
    detail: "configuration 'claude-3-5-sonnet' ran 2 of 5 required repetitions"
    affected_configs: ["claude-3-5-sonnet"]
```

### `missing_evidence`

One or more result matrix cells have no evaluation attached. This happens when a task timed out, the subprocess crashed before producing output, or the LLM judge was unavailable.

```yaml
caveats:
  - kind: missing_evidence
    detail: "3 cells in the result matrix have no EvaluationResult"
    affected_cells: ["task-stress/gpt-4o/rep-2", "task-stress/gpt-4o/rep-3"]
```

### `config_drift`

A configuration ID was reused across runs but the configuration content changed (different model, different timeout, different skill path). This makes historical trend comparison unreliable.

```yaml
caveats:
  - kind: config_drift
    detail: "configuration 'prod-agent' had model=claude-3-5-sonnet in run-001, model=claude-opus-4 in run-002"
    affected_configs: ["prod-agent"]
```

### `mixed_isolation`

Different isolation levels (`logical`, `os_policy`, `container`, `vm`) were used across configurations in the same run. Results from a sandboxed environment may not be comparable to results from a logical-only worktree.

```yaml
caveats:
  - kind: mixed_isolation
    detail: "baseline used isolation=logical, candidate used isolation=os_policy"
    affected_configs: ["baseline", "candidate"]
```

::: tip Caveat Severity
`snapshot_mismatch` and `config_drift` are the most severe — they affect comparability, not just confidence. The others reduce confidence but do not invalidate the comparison outright.
:::

## Evidence Chain Navigation

Every claim in a DecisionReport is backed by a traversable chain of evidence:

```
DecisionReport
  └── aggregation (per_configuration stats)
        └── evaluation_refs[]
              └── EvaluationResult (per task × config × rep)
                    └── evidence_refs[]
                          └── EvidenceItem
                                └── ArtifactRef (stdout, stderr, file diff, trace)
```

The web UI (`micro-eval ui`) renders this chain interactively. In the Comparison view, clicking any cell in the ResultMatrix opens the EvaluationResult, and from there you can navigate to the raw artifacts and Langfuse trace (if configured).

From the CLI, you can inspect the chain directly:

```bash
# Show the top-level decision for a run
micro-eval report --run-id abc123 --format json | jq '.decision'

# List all evaluation files for a run
ls .micro-eval/runs/abc123/evals/

# Open the artifact for a specific cell
cat .micro-eval/runs/abc123/artifacts/task-refactor/claude-3-5-sonnet/rep-1/stdout.txt
```

## Cross-Language Consistency

The decision logic is implemented in two places:

- **Python**: `micro_eval/evaluation/decision.py` — `build_decision(run_result: RunResult) -> DecisionReport`
- **TypeScript**: `ui/lib/decision.ts` — `recomputeDecision(runResult: RunResult): DecisionReport`

Both implementations are contract-tested against a shared golden fixture set in `tests/contract/test_decision_contract.py`. If the outputs diverge for any fixture, CI fails.

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

The shared Pydantic schema (Python) and zod schema (TypeScript) ensure both sides agree on field names, types, and allowed enum values. Any schema change must be updated in both places.

## not_comparable — What To Do

::: danger `not_comparable` blocks all comparisons
If the verdict is `not_comparable`, **no score, pass rate, or latency comparison is valid**. The configurations were not running in the same environment. Fix the snapshot issue before re-running.
:::

Common causes and fixes:

| Cause | Fix |
|---|---|
| Different git commits across runs | Pin `workspace.git_repo.ref` to the same commit hash in both configurations |
| Workspace setup commands changed | Bump the run — do not reuse the same run ID after changing setup |
| Configuration content changed but ID reused | Create a new configuration ID; do not mutate existing ones |
| Different isolation levels | Set the same `isolation` level in all configurations in a run |

To check what snapshot each configuration used:

```bash
micro-eval report --run-id abc123 --format json \
  | jq '.configurations[].same_start_snapshot'
```

If the `same_start_snapshot` hashes differ across configurations, the run is `not_comparable` by definition.

## Confidence Degradation Rules

Confidence starts at `high` and degrades:

1. Any `snapshot_mismatch` or `config_drift` caveat → verdict forced to `not_comparable`, confidence set to `low`
2. Any `low_sample` caveat → confidence drops one level (high → medium, medium → low)
3. Any `missing_evidence` caveat → confidence drops one level
4. Any `mixed_isolation` caveat → confidence drops one level
5. If two or more non-snapshot caveats are present → confidence set to `low`

The final `confidence` value reflects the cumulative effect of all active caveats.

## Next Steps

- [Workspace Isolation](/guide/workspace-isolation) — understand the four isolation levels and how `same_start_snapshot` is computed
