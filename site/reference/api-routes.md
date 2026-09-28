# API Routes

The micro-eval Web UI is served by a local Next.js dev server. All API routes read from `.micro-eval/` JSON files on disk — there is no remote server, no database connection, and no authentication layer. The API is strictly local-only. In **server mode** (`micro-eval serve`), additional workspace-scoped and queue management routes become available — see [Server Mode API Routes](#server-mode-api-routes) below.

::: tip Starting the server
```bash
uv run micro-eval ui
# Server starts at http://localhost:3000
```
All routes below are relative to `http://localhost:3000`.
:::

## Overview

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/api/runs` | List all run records |
| `GET` | `/api/runs/[id]` | Get a single run with full detail |
| `GET` | `/api/runs/[id]/cells/[cellId]` | Get a single cell result |
| `POST` | `/api/runs/[id]/cells/[cellId]/evaluate` | Append a human evaluation |
| `GET` | `/api/runs/[id]/cells/[cellId]/trace` | Get trace data for a cell |
| `GET` | `/api/runs/[id]/artifacts` | List artifacts for a run |
| `GET` | `/api/trends` | Query cross-run trend data |

---

## GET /api/runs

List all run records found in `.micro-eval/runs/`. Each record is loaded from its `run.json` file. Results are returned in reverse chronological order (newest first).

**Response:** `RunRecord[]`

```bash
curl http://localhost:3000/api/runs
```

**Example response:**

```json
[
  {
    "id": "run_20260614_171843",
    "timestamp": "2026-06-14T17:18:43Z",
    "status": "completed",
    "config_path": "eval.yaml",
    "task_count": 3,
    "config_count": 2,
    "repetitions": 2,
    "cell_count": 12,
    "pass_count": 9,
    "error_count": 1,
    "decision": "improved",
    "duration_s": 87.4
  },
  {
    "id": "run_20260611_090155",
    "timestamp": "2026-06-11T09:01:55Z",
    "status": "completed",
    "config_path": "eval.yaml",
    "task_count": 3,
    "config_count": 2,
    "repetitions": 2,
    "cell_count": 12,
    "pass_count": 7,
    "error_count": 0,
    "decision": "inconclusive",
    "duration_s": 94.1
  }
]
```

**Decision values:** `improved` | `regressed` | `mixed` | `inconclusive` | `not_comparable` | `needs_human_review`

---

## GET /api/runs/[id]

Get a single run record with full detail, including all cell results, artifacts, evidence, and evaluations. This endpoint reads and merges all files within `.micro-eval/runs/<id>/`.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Run ID (e.g. `run_20260614_171843`) |

**Response:** Full `RunRecord` with embedded results.

```bash
curl http://localhost:3000/api/runs/run_20260614_171843
```

**Example response:**

```json
{
  "id": "run_20260614_171843",
  "timestamp": "2026-06-14T17:18:43Z",
  "status": "completed",
  "plan": {
    "tasks": ["refactor", "add-tests", "fix-bug"],
    "configurations": ["sonnet-skill-v1", "sonnet-skill-v2"],
    "repetitions": 2,
    "execution_seed": null
  },
  "result_matrix": {
    "cells": [
      {
        "id": "refactor__sonnet-skill-v1__0",
        "task_id": "refactor",
        "config_id": "sonnet-skill-v1",
        "rep_index": 0,
        "status": "pass",
        "exit_code": 0,
        "duration_ms": 4210,
        "cost_usd": 0.008,
        "validation_results": [
          { "type": "exit_code", "passed": true },
          { "type": "contains", "passed": true }
        ],
        "judge_score": null,
        "human_score": null
      }
    ]
  },
  "decision": {
    "status": "improved",
    "winning_config": "sonnet-skill-v2",
    "caveats": []
  },
  "artifacts": [],
  "metadata": {
    "workspace_provider": "logical",
    "isolation_level": "logical"
  }
}
```

::: warning Large runs
Runs with many cells and large artifacts may produce substantial JSON. The UI paginates the result matrix display, but this endpoint always returns the full payload. For scripting, prefer `/api/runs/[id]/cells/[cellId]` to fetch individual cells.
:::

---

## GET /api/runs/[id]/cells/[cellId]

Get a single cell result. The cell ID encodes its coordinates in the run matrix.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Run ID |
| `cellId` | string | Cell ID in the form `<task_id>__<config_id>__<rep_index>` |

**Response:** `CellResult`

```bash
curl http://localhost:3000/api/runs/run_20260614_171843/cells/refactor__sonnet-skill-v1__0
```

**Example response:**

```json
{
  "id": "refactor__sonnet-skill-v1__0",
  "task_id": "refactor",
  "config_id": "sonnet-skill-v1",
  "rep_index": 0,
  "status": "pass",
  "exit_code": 0,
  "exit_reason": "normal",
  "duration_ms": 4210,
  "cost_usd": 0.008,
  "stdout": "Refactoring complete. 14 functions updated.",
  "stderr": "",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "validation_results": [
    {
      "type": "exit_code",
      "passed": true,
      "expected": 0,
      "actual": 0
    },
    {
      "type": "contains",
      "passed": true,
      "stream": "stdout",
      "value": "refactoring complete",
      "case_sensitive": false
    }
  ],
  "judge_score": null,
  "judge_error": null,
  "human_score": null,
  "trace_ref": {
    "trace_id": "tr_abc123",
    "langfuse_url": "https://cloud.langfuse.com/trace/tr_abc123"
  }
}
```

**Cell status values:**

| Status | Meaning |
|--------|---------|
| `pass` | All expectations passed |
| `fail` | One or more expectations failed |
| `error` | Setup failure, agent crash, or timeout before expectations ran |
| `skipped` | Cell was not executed (e.g. `stop_on_cell_error` triggered) |

---

## POST /api/runs/[id]/cells/[cellId]/evaluate

Append a human evaluation score and comment to a cell. This is the primary write endpoint in the API — all other routes are read-only.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Run ID |
| `cellId` | string | Cell ID |

**Request body:**

```json
{
  "score": 8,
  "comment": "Output is correct but could be more concise.",
  "evaluator": "alice"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `score` | number (0–10) | Yes | Human quality score |
| `comment` | string | Yes | Free-text annotation |
| `evaluator` | string | No | Evaluator identifier; defaults to `"human"` |

**Side effects:**

1. Writes the evaluation entry to `.micro-eval/runs/<id>/cells/<cellId>/evaluation.json`
2. Recomputes `decision.json` for the run, potentially updating the overall decision status

**Response:** Updated `EvaluationResult`

```bash
curl -X POST http://localhost:3000/api/runs/run_20260614_171843/cells/refactor__sonnet-skill-v1__0/evaluate \
  -H "Content-Type: application/json" \
  -d '{"score": 8, "comment": "Output is correct but could be more concise.", "evaluator": "alice"}'
```

**Example response:**

```json
{
  "cell_id": "refactor__sonnet-skill-v1__0",
  "score": 8,
  "comment": "Output is correct but could be more concise.",
  "evaluator": "alice",
  "timestamp": "2026-06-15T10:22:05Z",
  "decision_updated": true,
  "new_decision_status": "needs_human_review"
}
```

::: tip When decision status changes
If the new human score causes the overall run decision to change (for example, previously `inconclusive` cells now have enough annotations to reach `improved`), the response includes `decision_updated: true` and the updated `new_decision_status`. Reload the run view to see the updated matrix.
:::

::: warning No authentication
This endpoint writes to disk without any authentication check. It is designed for single-user local use only. Do not expose the micro-eval UI server on a public network interface.
:::

---

## GET /api/runs/[id]/cells/[cellId]/trace

Get trace data for a cell. The trace reference is resolved from the cell's `trace_ref` manifest entry, which was recorded at execution time by the Langfuse integration.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Run ID |
| `cellId` | string | Cell ID |

**Response:** `TraceRef` with summary

```bash
curl http://localhost:3000/api/runs/run_20260614_171843/cells/refactor__sonnet-skill-v1__0/trace
```

**Example response (trace available):**

```json
{
  "cell_id": "refactor__sonnet-skill-v1__0",
  "trace_id": "tr_abc123",
  "langfuse_url": "https://cloud.langfuse.com/trace/tr_abc123",
  "summary": {
    "total_tokens": 3820,
    "prompt_tokens": 1240,
    "completion_tokens": 2580,
    "total_cost_usd": 0.008,
    "duration_ms": 4210,
    "model": "claude-sonnet-4-5",
    "span_count": 7
  }
}
```

**Example response (no trace configured):**

```json
{
  "cell_id": "refactor__sonnet-skill-v1__0",
  "trace_id": null,
  "langfuse_url": null,
  "summary": null,
  "reason": "Langfuse credentials not configured at run time"
}
```

::: tip Configuring Langfuse
Trace data is captured at run time, not on demand. To see traces, set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (as `LANGFUSE_SECRET_KEY`), and `LANGFUSE_HOST` before invoking `micro-eval run`. See [Execution → Trace Capture](/guide/execution#step-6-trace-capture-optional) for details.
:::

---

## GET /api/runs/[id]/artifacts

List all artifacts for a run. Artifact references are read from the run's artifact manifest at `.micro-eval/runs/<id>/artifacts/manifest.json`. Actual artifact content is served separately via the static file path in each `ArtifactRef`.

**Path parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | string | Run ID |

**Response:** `ArtifactRef[]`, filtered to artifacts within the run's boundary.

```bash
curl http://localhost:3000/api/runs/run_20260614_171843/artifacts
```

**Example response:**

```json
[
  {
    "artifact_id": "art_0001",
    "cell_id": "refactor__sonnet-skill-v1__0",
    "name": "output/report.md",
    "content_type": "text/markdown",
    "size_bytes": 4820,
    "digest": "sha256:a1b2c3d4...",
    "static_path": "/api/runs/run_20260614_171843/artifacts/art_0001/content",
    "truncated": false,
    "warning": null
  },
  {
    "artifact_id": "art_0002",
    "cell_id": "fix-bug__sonnet-skill-v2__1",
    "name": "output/patch.diff",
    "content_type": "text/x-diff",
    "size_bytes": 10485761,
    "digest": "sha256:e5f6a7b8...",
    "static_path": null,
    "truncated": true,
    "warning": "Artifact exceeds max_artifact_bytes (10 MB). Content not stored. Digest only."
  }
]
```

**ArtifactRef fields:**

| Field | Type | Description |
|-------|------|-------------|
| `artifact_id` | string | Stable artifact identifier within the run |
| `cell_id` | string | Cell that produced this artifact |
| `name` | string | Original path relative to the workspace root |
| `content_type` | string | MIME type, inferred from extension |
| `size_bytes` | number | Size at capture time |
| `digest` | string | SHA-256 content digest |
| `static_path` | string \| null | URL path to fetch artifact content; `null` if not stored |
| `truncated` | boolean | `true` if content exceeded `max_artifact_bytes` |
| `warning` | string \| null | Human-readable note for boundary violations or missing content |

::: warning Artifacts with warnings
When `truncated` is `true` or `warning` is non-null, `static_path` will be `null` — there is no content to serve. The digest is still recorded for integrity verification if you have the original file. Increase `run.guardrails.max_artifact_bytes` in your `eval.yaml` to capture larger artifacts in future runs.
:::

---

## GET /api/trends

Query cross-run trend data for a specific configuration. The response is assembled from the SQLite index (`.micro-eval/index.db`) and includes drift breakpoints where the configuration digest changed between runs.

**Query parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `config_id` | string | Yes | — | Configuration ID to query |
| `since` | string (ISO-8601) | No | *(all runs)* | Exclude runs before this timestamp |
| `limit` | number | No | `50` | Maximum number of data points to return |

**Response:** Trend series with breakpoint annotations.

::: code-group

```bash [basic]
curl "http://localhost:3000/api/trends?config_id=sonnet-skill-v2"
```

```bash [with filters]
curl "http://localhost:3000/api/trends?config_id=sonnet-skill-v2&since=2026-06-01T00:00:00Z&limit=10"
```

:::

**Example response:**

```json
{
  "config_id": "sonnet-skill-v2",
  "data_points": [
    {
      "run_id": "run_20260610_143022",
      "timestamp": "2026-06-10T14:30:22Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.72,
      "mean_latency_ms": 4200,
      "p50_latency_ms": 4100,
      "p95_latency_ms": 9800,
      "cost": 0.031
    },
    {
      "run_id": "run_20260611_090155",
      "timestamp": "2026-06-11T09:01:55Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.75,
      "mean_latency_ms": 4050,
      "p50_latency_ms": 3950,
      "p95_latency_ms": 9500,
      "cost": 0.029
    },
    {
      "run_id": "run_20260614_171843",
      "timestamp": "2026-06-14T17:18:43Z",
      "digest": "c1d7a412",
      "pass_rate": 0.81,
      "mean_latency_ms": 3700,
      "p50_latency_ms": 3650,
      "p95_latency_ms": 8200,
      "cost": 0.027
    }
  ],
  "breakpoints": [
    {
      "run_id": "run_20260614_171843",
      "reason": "digest changed: a3f9c2b1 → c1d7a412",
      "timestamp": "2026-06-14T17:18:43Z"
    }
  ]
}
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `config_id` | string | The queried configuration ID |
| `data_points` | array | Time-ordered list of per-run metrics |
| `data_points[].run_id` | string | Run identifier |
| `data_points[].timestamp` | string | Run completion time (ISO-8601) |
| `data_points[].digest` | string | Configuration digest at time of run |
| `data_points[].pass_rate` | number | Fraction of cells that passed (0.0–1.0) |
| `data_points[].mean_latency_ms` | number | Mean cell wall-clock duration |
| `data_points[].p50_latency_ms` | number | Median cell duration |
| `data_points[].p95_latency_ms` | number | 95th-percentile cell duration |
| `data_points[].cost` | number | Total run cost in USD (requires Langfuse) |
| `breakpoints` | array | Drift breakpoints between consecutive data points |
| `breakpoints[].run_id` | string | First run after the digest changed |
| `breakpoints[].reason` | string | Human-readable description of the digest change |
| `breakpoints[].timestamp` | string | Timestamp of the first post-breakpoint run |

::: warning Comparing across breakpoints
Data points on either side of a breakpoint belong to different effective configurations. Do not draw conclusions from pass rate changes that span a breakpoint — the change may be caused by the configuration difference rather than the agent's quality. See [Trend Analysis → Drift-Aware Breakpoints](/guide/trend-analysis#drift-aware-breakpoints) for details.
:::

::: tip Rebuilding the index
The `/api/trends` route reads from the SQLite index. If the index is missing or stale, rebuild it:
```bash
uv run micro-eval index import-json
```
:::

---

## Error Responses

All routes return standard HTTP error codes. Error bodies always include a `detail` field.

```json
{
  "error": "not_found",
  "detail": "Run run_20260601_000000 not found in .micro-eval/runs/"
}
```

| Status | Condition |
|--------|-----------|
| `400 Bad Request` | Missing required query parameter; invalid body schema |
| `404 Not Found` | Run ID or cell ID does not exist on disk |
| `409 Conflict` | Concurrent write detected (e.g. two evaluate calls to the same cell) |
| `422 Unprocessable Entity` | Body passes JSON parsing but fails field validation |
| `500 Internal Server Error` | Disk read error, corrupted JSON, or index failure |

::: danger Corrupted run files
If a `run.json` or `plan.json` is truncated or malformed (for example, from a crash mid-write), the affected run will return `500` from all its routes. Other runs are not affected. Inspect the file directly and remove it if needed — the index entry will remain stale until you run `micro-eval index import-json` again.
:::

---

## Local-Only Design

The API has no authentication, no rate limiting, and no CORS headers. It is designed to be used only on `localhost` by the browser tab that the `micro-eval ui` command opens.

::: danger Do not expose to the network
Do not bind the Next.js server to `0.0.0.0` or proxy it through a public-facing server. The write endpoint (`POST /evaluate`) has no access control, and `.micro-eval/` run data may contain sensitive agent outputs or secrets that were not fully redacted before artifact capture.
:::

## Related Pages

- [Trend Analysis](/guide/trend-analysis) — how the SQLite index and drift breakpoints work
- [Evaluation & Scoring](/guide/evaluation) — the three-layer scoring pipeline (deterministic → LLM judge → human)
- [Security Model](/guide/security) — secrets redaction, workspace boundaries, and subprocess isolation
- [Web UI](/reference/web-ui) — the browser interface that consumes these routes

---

## Server Mode API Routes

These routes are only available when running `micro-eval serve`. In local mode (`micro-eval ui`) they return `404`.

::: warning Intranet only
Server mode routes have **no authentication**. Identity is self-reported via the `X-Micro-Eval-Member` HTTP header and is used for attribution only, not access control. Deploy only on a trusted private network.
:::

::: info Notes
- **Server mode routes return 404 when not running in server mode.**
- **All write routes require `X-Micro-Eval-Member` header and `Content-Type: application/json`.**
:::

### Overview

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/api/workspaces` | List all workspaces |
| `POST` | `/api/workspaces` | Create a new workspace |
| `GET` | `/api/workspaces/[id]` | Get workspace metadata |
| `PATCH` | `/api/workspaces/[id]` | Update workspace metadata |
| `DELETE` | `/api/workspaces/[id]` | Delete a workspace |
| `GET` | `/api/workspaces/[id]/runs` | List runs in a workspace |
| `POST` | `/api/workspaces/[id]/runs/enqueue` | Enqueue a new run job |
| `GET` | `/api/workspaces/[id]/runs/[runId]` | Get a run within a workspace |
| `GET` | `/api/workspaces/[id]/config` | Get the workspace eval.yaml |
| `GET` | `/api/workspaces/[id]/trends` | Query workspace-scoped trend data |
| `GET` | `/api/queue` | Get queue dashboard summary |
| `GET` | `/api/jobs/[jobId]` | Get a single job record |
| `POST` | `/api/jobs/[jobId]/cancel` | Cancel a queued or running job |
| `GET` | `/api/templates` | List all templates |
| `GET` | `/api/templates/[id]` | Get a single template |
| `GET` | `/api/server/status` | Server health and process info |

---

### Workspace Routes

**GET /api/workspaces** — Returns a list of `WorkspaceMeta` objects, ordered by `last_run_at` descending. Archived workspaces are excluded by default; pass `?include_archived=true` to include them.

**POST /api/workspaces** — Create a new workspace. Body fields: `name` (required), `owner` (required), `template_id`, `description`. Returns the created `WorkspaceMeta`.

**GET /api/workspaces/[id]** — Get full metadata for a single workspace.

**PATCH /api/workspaces/[id]** — Update `name`, `description`, or `status` (`active` | `archived`). Returns the updated `WorkspaceMeta`.

**DELETE /api/workspaces/[id]** — Delete the workspace and all associated run data. Returns `204 No Content`. This is irreversible.

**GET /api/workspaces/[id]/config** — Returns the raw `eval.yaml` content for the workspace as `text/plain`.

**GET /api/workspaces/[id]/trends** — Same shape as the local `/api/trends` route but scoped to this workspace's runs. Accepts `config_id`, `since`, and `limit` query parameters.

---

### Run Enqueue and Status

**GET /api/workspaces/[id]/runs** — List all runs for a workspace in reverse chronological order. Returns `RunRecord[]` summaries.

**POST /api/workspaces/[id]/runs/enqueue** — Enqueue a new evaluation run for this workspace. The worker picks it up and executes it serially.

Request body:

```json
{
  "overrides": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `overrides` | object | No | JSON overrides applied on top of the workspace `eval.yaml` before the plan is built. |

Response: the created `Job` record (status: `queued`).

Required headers: `X-Micro-Eval-Member`, `Content-Type: application/json`.

**GET /api/workspaces/[id]/runs/[runId]** — Get a completed run record within a workspace. Same shape as the local `/api/runs/[id]` route.

---

### Queue Routes

**GET /api/queue** — Returns a summary of the entire queue across all workspaces.

```json
{
  "queued": 2,
  "running": 1,
  "done_today": 14,
  "jobs": [ /* Job records, most recent first */ ]
}
```

**GET /api/jobs/[jobId]** — Get a single `Job` record by ID. Includes `status`, `progress`, timestamps, and any error message.

**POST /api/jobs/[jobId]/cancel** — Request cancellation of a queued or running job. Queued jobs are cancelled immediately. Running jobs finish the current cell, then stop. Body: `{}`. Required headers: `X-Micro-Eval-Member`, `Content-Type: application/json`.

---

### Template Routes

Templates are managed via the CLI (`micro-eval template create/update/delete`) and are **read-only** through the browser API.

**GET /api/templates** — List all templates as `TemplateMeta[]`.

**GET /api/templates/[id]** — Get a single template's metadata. Does not return the template file contents; use the CLI to inspect files.

---

### Server Status

**GET /api/server/status** — Returns basic server health information.

```json
{
  "server_mode": true,
  "configured": true,
  "workspace_count": 3,
  "template_count": 1,
  "queue": {
    "queued": 2,
    "running": 1
  },
  "ui_version": "0.4.6"
}
```
