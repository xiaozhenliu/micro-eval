# Data Model

micro-eval stores all evaluation data as JSON files under `.micro-eval/runs/<run-id>/`. Every structure is defined with Pydantic on the Python side and mirrored with zod on the TypeScript side, ensuring a single source of truth across the CLI and the Web UI.

::: tip File layout
```
.micro-eval/
  runs/
    <run-id>/
      run.json          # RunRecord
      cells/
        <cell-id>.json  # CellResult
      artifacts/        # Binary and text artifacts
  index.sqlite          # Trend index (read-only projection of JSON)
```
:::

---

## RunRecord

The top-level record written when a run completes. It captures the full configuration matrix, all cell results, the reproducibility snapshot, and the final decision.

| Field | Type | Description |
|---|---|---|
| `id` | `string` | UUID v4. Stable across retries. |
| `project_name` | `string` | Name from `eval.yaml`. |
| `status` | `"planned" \| "running" \| "completed" \| "failed" \| "partial"` | Lifecycle status. `partial` means some cells errored. |
| `created_at` | `string` | ISO-8601 UTC timestamp. |
| `completed_at` | `string \| null` | Set when the run finishes or fails. |
| `output_dir` | `string` | Absolute path to `.micro-eval/runs/<run-id>/`. |
| `config_hash` | `string` | SHA-256 of the canonical eval.yaml used. |
| `tasks` | `TaskSpec[]` | Inline copies of every task definition. |
| `configurations` | `ConfigurationSpec[]` | Inline copies of every configuration definition. |
| `cells` | `CellSpec[]` | Flat list of `(task, configuration, repetition)` triples. |
| `results` | `CellResult[]` | One entry per cell. May be a partial list during `running`. |
| `execution_order` | `string[]` | Ordered list of `cell_id`s actually executed. |
| `execution_seed` | `integer` | Random seed used to shuffle execution order. |
| `same_start_snapshot` | `SameStartSnapshot` | Reproducibility envelope captured before execution. |
| `replay_canonical` | `string` | CLI command to reproduce this run exactly. |
| `artifacts` | `ArtifactRef[]` | Run-level artifacts (e.g. combined report PDF). |
| `evidence` | `EvidenceItem[]` | Run-level evidence items. |
| `traces` | `TraceRef[]` | Run-level Langfuse trace references. |
| `evaluations` | `EvaluationResult[]` | All evaluation results across all cells. |
| `decision` | `DecisionReport \| null` | Final verdict. `null` until all cells complete. |
| `denominator_policy` | `"all_cells" \| "successful_cells"` | How pass rates are computed across the run. |

```json
{
  "id": "run-2026-0615-a3f9",
  "project_name": "pr-review-agent",
  "status": "completed",
  "created_at": "2026-06-15T09:00:00Z",
  "completed_at": "2026-06-15T09:04:22Z",
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
  "denominator_policy": "successful_cells"
}
```

---

## CellResult

A single cell is one `(task, configuration, repetition)` execution. CellResult holds the raw outputs, scores, and metadata for that execution.

| Field | Type | Description |
|---|---|---|
| `cell_id` | `string` | Stable ID derived from `task_id + config_id + repetition`. |
| `run_id` | `string` | Parent `RunRecord.id`. |
| `task_id` | `string` | Task identifier from `eval.yaml`. |
| `configuration_id` | `string` | Configuration identifier from `eval.yaml`. |
| `configuration_name` | `string` | Human-readable configuration label. |
| `repetition` | `integer` | 0-indexed repetition number. |
| `status` | `"pass" \| "fail" \| "error" \| "timeout"` | Execution outcome. |
| `score` | `float \| null` | Aggregate score in [0, 1]. |
| `pass_fail` | `boolean \| null` | Deterministic pass/fail after all evaluators run. |
| `output_summary` | `string \| null` | First 500 chars of agent output. |
| `stdout_summary` | `string \| null` | First 500 chars of stdout. |
| `stderr_summary` | `string \| null` | First 500 chars of stderr. |
| `exit_code` | `integer \| null` | Process exit code. |
| `latency_s` | `float` | Wall-clock execution time in seconds. |
| `failure_mode` | `string \| null` | Categorised failure label when `status != "pass"`. |
| `stdout_truncated` | `boolean` | Whether stdout was truncated to summary. |
| `stderr_truncated` | `boolean` | Whether stderr was truncated to summary. |
| `output_truncated` | `boolean` | Whether agent output was truncated. |
| `artifact_refs` | `ArtifactRef[]` | Cell-scoped artifacts (diff, output file, etc.). |
| `evidence_refs` | `string[]` | IDs of `EvidenceItem` entries related to this cell. |
| `evaluation_refs` | `string[]` | IDs of `EvaluationResult` entries for this cell. |
| `trace_refs` | `TraceRef[]` | Langfuse trace links for this cell. |
| `cell_snapshot` | `object \| null` | Point-in-time workspace snapshot taken after execution. |
| `snapshot_gate_result` | `"pass" \| "fail" \| "skipped"` | Whether the cell passed the snapshot comparability gate. |

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

The final verdict computed after all cells complete. It aggregates per-configuration statistics and assigns a `DecisionStatus` with a confidence level.

| Field | Type | Description |
|---|---|---|
| `decision_report_id` | `string` | UUID. |
| `verdict` | `DecisionStatus` | One of six statuses (see below). |
| `confidence` | `"high" \| "medium" \| "low"` | Confidence in the verdict. |
| `evaluation_refs` | `string[]` | Evaluation IDs that informed the verdict. |
| `evidence_refs` | `string[]` | Evidence IDs that informed the verdict. |
| `caveats` | `string[]` | Human-readable caveats (e.g. "only 2 repetitions"). |
| `aggregation` | `AggregationResult` | Per-configuration `ConfigurationStats`. |
| `timestamp` | `string` | ISO-8601 UTC timestamp when the report was generated. |
| `recommended_action` | `string \| null` | Optional free-text recommendation. |

**DecisionStatus values:**

| Status | Meaning |
|---|---|
| `improved` | The challenger configuration is statistically better. |
| `regressed` | The challenger configuration is statistically worse. |
| `mixed` | Some tasks improved, others regressed. |
| `inconclusive` | Results are within noise — no clear winner. |
| `not_comparable` | Cells ran under different starting conditions. |
| `needs_human_review` | LLM judge or auto-evaluators could not reach a verdict. |

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

Aggregated statistics for one configuration across all tasks and repetitions in a run. Used inside `DecisionReport.aggregation`.

| Field | Type | Description |
|---|---|---|
| `n_cells` | `integer` | Total cells for this configuration. |
| `n_successful` | `integer` | Cells that did not error or timeout. |
| `pass_rate` | `float` | Fraction of denominator cells that passed. |
| `pass_at_k` | `float \| null` | Pass-at-k: probability at least one of k repetitions passes. |
| `pass_hat_k` | `float \| null` | Pass-hat-k: expected fraction of k repetitions that pass. |
| `mean_latency_ms` | `float \| null` | Mean wall-clock time across successful cells, in ms. |
| `median_latency_ms` | `float \| null` | Median wall-clock time, in ms. |
| `total_cost` | `CostMetric` | Summed cost across all cells in this configuration. |
| `denominator_policy` | `"all_cells" \| "successful_cells"` | Which cells contribute to `pass_rate`. |
| `caveats` | `string[]` | e.g. `["2 cells timed out"]`. |

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

One evaluation pass over a single cell. Multiple evaluators may run per cell (deterministic validator, LLM judge, human annotation), each producing a separate `EvaluationResult`.

| Field | Type | Description |
|---|---|---|
| `evaluation_id` | `string` | UUID. |
| `cell_id` | `string` | The cell this evaluation covers. |
| `evaluator_type` | `"deterministic" \| "llm_judge" \| "human"` | Category of evaluator. |
| `evaluator` | `string` | Evaluator name or model (e.g. `"exit_code_validator"`, `"claude-3-7-sonnet"`). |
| `pass_fail` | `"pass" \| "fail" \| null` | Binary verdict. `null` when score-only. |
| `score` | `float \| null` | Numeric score in [0, 1]. |
| `scores` | `object` | Dimension-level scores (e.g. `{"correctness": 0.9, "style": 0.7}`). |
| `evaluator_meta` | `object` | Evaluator-specific metadata (model params, tokens used, etc.). |
| `rubric_hash` | `string \| null` | SHA-256 of the rubric used for LLM judge or human. |
| `comment` | `string \| null` | Free-text reasoning from the evaluator. |
| `evidence_refs` | `string[]` | IDs of `EvidenceItem` entries supporting this evaluation. |
| `created_at` | `string` | ISO-8601 UTC timestamp. |

::: tip Evaluation pipeline
micro-eval runs evaluators in order: **deterministic validator → LLM judge → human annotation**. Each stage is optional. A cell with a failing deterministic check does not proceed to the LLM judge unless you explicitly configure it.
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

A pointer to a file artifact produced by an agent or the evaluation pipeline. The file lives under `.micro-eval/runs/<run-id>/artifacts/`.

| Field | Type | Description |
|---|---|---|
| `artifact_id` | `string` | UUID. |
| `kind` | `string` | Semantic type: `"diff"`, `"output_file"`, `"log"`, `"report"`, `"screenshot"`, etc. |
| `path` | `string` | Relative path from `output_dir`. |
| `sha256` | `string` | Content hash for integrity verification. |
| `size_bytes` | `integer` | File size. |
| `media_type` | `string` | MIME type (e.g. `"text/plain"`, `"application/json"`). |
| `redacted` | `boolean` | `true` if secret values were scrubbed before storage. |
| `warning` | `string \| null` | Set when redaction was partial or file is suspect. |

::: warning Secret redaction
Any artifact whose content matches a `MICRO_EVAL_SECRET_*` environment variable pattern is automatically redacted before being written to disk. The `redacted` flag is set to `true` and `warning` is populated with the redaction summary.
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

A link to an external Langfuse trace. Traces are optional — they are only written when Langfuse is configured.

| Field | Type | Description |
|---|---|---|
| `trace_id` | `string` | Langfuse trace ID (or local UUID if Langfuse is unavailable). |
| `provider` | `"langfuse" \| "local"` | Where the full trace is stored. |
| `external_url` | `string \| null` | Direct URL to the Langfuse trace viewer. |
| `cost` | `CostMetric` | Cost attributed to this trace. |
| `summary` | `string \| null` | Short description of what was traced. |

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

A structured piece of evidence supporting an evaluation verdict. Evidence items link raw observations (stdout, diffs, test results) to the evaluation layer.

| Field | Type | Description |
|---|---|---|
| `evidence_id` | `string` | UUID. |
| `kind` | `string` | `"test_result"`, `"diff"`, `"log_excerpt"`, `"assertion"`, `"human_note"`, etc. |
| `summary` | `string` | One-sentence description of what this evidence shows. |
| `source_kind` | `"stdout" \| "stderr" \| "artifact" \| "evaluator" \| "human"` | Where the evidence came from. |
| `source_ref` | `string \| null` | ID of the source (e.g. `artifact_id` or `evaluation_id`). |
| `cell_id` | `string \| null` | Cell this evidence is scoped to. `null` for run-level evidence. |
| `status` | `"pass" \| "fail" \| "info"` | Whether this evidence is positive, negative, or neutral. |
| `severity` | `"critical" \| "major" \| "minor" \| "info"` | Impact weight for verdict aggregation. |
| `artifact_refs` | `ArtifactRef[]` | Supporting artifact files. |
| `metadata` | `object` | Freeform key-value data (e.g. `{"test_name": "test_parser"}`). |

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

Captured before execution begins. The snapshot verifies that all cells in a run started from identical conditions. Cells that fail the snapshot gate are marked `not_comparable`.

| Field | Type | Description |
|---|---|---|
| `workspace_type` | `"blank" \| "files" \| "git_repo"` | How the workspace was initialised. |
| `git_commit` | `string \| null` | HEAD commit SHA at snapshot time. `null` for non-git workspaces. |
| `dirty` | `boolean` | Whether the working tree had uncommitted changes. |
| `config_hash` | `string` | SHA-256 of the eval.yaml that was used. |
| `configuration_digests` | `object` | Map of `config_id → digest` for each configuration's resolved parameters. |
| `task_revisions` | `object` | Map of `task_id → content_hash` for each task definition. |
| `python_version` | `string` | Python version string (e.g. `"3.11.9"`). |
| `setup_commands_digest` | `string \| null` | Hash of the concatenated setup commands. |
| `guardrails_digest` | `string \| null` | Hash of the active guardrail policy file. |
| `sandbox_policy` | `string` | Isolation level: `"logical"`, `"os_policy"`, `"container"`, or `"vm"`. |
| `network_policy` | `string` | Network access policy: `"none"`, `"localhost"`, `"unrestricted"`. |
| `toolchain_fingerprint` | `object` | Key tool versions (e.g. `{"uv": "0.4.1", "node": "22.0.0"}`). |
| `fixture_digests` | `object` | Map of fixture path → SHA-256 for multi-source fixtures. |
| `timestamp` | `string` | ISO-8601 UTC timestamp. |
| `caveats` | `string[]` | Snapshot warnings (e.g. `["dirty working tree"]`). |

::: warning Dirty working tree
If `dirty: true` the run will complete, but `DecisionReport.verdict` may be set to `not_comparable` because the workspace state cannot be reproduced exactly. Commit or stash your changes before running evaluations that require high reproducibility.
:::

::: tip Sandbox policies
| Policy | Mechanism | Use case |
|---|---|---|
| `logical` | git worktree | Default. Fast, no OS isolation. |
| `os_policy` | Seatbelt (macOS) / Bubblewrap (Linux) | Restricts filesystem and network without containers. |
| `container` | Docker / OCI | Full container isolation. |
| `vm` | E2B / Modal | Remote cloud execution. Maximum isolation. |

If the requested policy is unavailable, `logical` is used as fallback and a caveat is added.
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

A monetary cost measurement attached to a trace or a configuration's aggregate statistics. `amount` may be `null` when cost data is unavailable (e.g. no Langfuse integration).

| Field | Type | Description |
|---|---|---|
| `amount` | `float \| null` | Cost amount. `null` means not available. |
| `currency` | `string` | ISO-4217 currency code. Defaults to `"USD"`. |
| `source` | `string` | Where the cost figure came from: `"langfuse"`, `"estimated"`, `"manual"`. |

```json
{
  "amount": 0.018,
  "currency": "USD",
  "source": "langfuse"
}
```

::: tip Cost availability
Cost data is only populated when Langfuse is configured via `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. When those variables are absent, micro-eval sets `amount: null` and `source: "unavailable"` rather than failing the run.
:::

---

## Schema validation

The full Pydantic schemas live in `micro_eval/schema/`. The zod mirrors live in `ui/src/lib/schema/`. Both are generated from the same canonical field definitions.

::: code-group

```python [Python (Pydantic)]
from micro_eval.schema import RunRecord, CellResult, DecisionReport

# Validate a run.json loaded from disk
with open(".micro-eval/runs/run-001/run.json") as f:
    data = json.load(f)

record = RunRecord.model_validate(data)
print(record.decision.verdict)  # "improved"
```

```typescript [TypeScript (zod)]
import { RunRecord } from "@/lib/schema/run";

// Used in Next.js API routes that read run.json
const raw = JSON.parse(fs.readFileSync(runJsonPath, "utf-8"));
const record = RunRecord.parse(raw);
console.log(record.decision?.verdict); // "improved"
```

:::
