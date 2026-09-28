# Web UI

The micro-eval Web UI is a **Next.js application served locally** alongside your project. It reads `.micro-eval/` JSON files through API routes — no database, no cloud, no authentication required.

::: tip Local mode
The Web UI binds to `localhost` and reads directly from your filesystem. Your evaluation data never leaves the machine. The above applies to `micro-eval ui`. Server mode (`micro-eval serve`) is designed for intranet access.
:::

## Launching

::: code-group

```bash [via CLI]
# Point to any project and start serving
MICRO_EVAL_PROJECT_ROOT=/path/to/project micro-eval ui --port 3000
```

```bash [via npm (source checkout)]
# From the ui/ directory with the env var set
export MICRO_EVAL_PROJECT_ROOT=/path/to/project
cd ui && npm run dev
```

:::

Once started, open `http://localhost:3000` in your browser.

::: warning Port conflicts
If port 3000 is already in use, pass `--port <number>` to pick a different one. The CLI will print the actual URL on startup.
:::

## Server Mode

`micro-eval serve` starts the team server — a Next.js production build plus a Python worker process — instead of the local single-user UI.

```bash
micro-eval serve --port 3000
```

Key differences from local mode:

- **Network binding** — binds to `0.0.0.0:3000` (network-accessible on the local subnet) instead of `localhost`.
- **Data directory** — stores all data in `~/.micro-eval-server/` (separate from the local `~/.micro-eval/` used by `micro-eval ui`).
- **Worker process** — a Python worker runs alongside the Next.js server and executes queued runs serially.
- **No authentication** — designed for trusted intranet use within a 1–20 person team. `X-Micro-Eval-Member` header is used for attribution only, not access control.

The existing `micro-eval ui` local mode is completely unchanged.

### Server Mode Pages

| Page | Description |
|---|---|
| `/` | Server dashboard — workspace grid and queue status (server mode home) |
| `/workspaces` | All workspaces (active and archived) |
| `/workspaces/new` | Create workspace form (from a template or blank) |
| `/workspace/[id]` | Workspace detail and run list |
| `/workspace/[id]/run/[runId]` | Run detail, scoped to the workspace |
| `/workspace/[id]/run/[runId]/review` | Review page, scoped to the workspace |
| `/workspace/[id]/config` | View and edit the workspace `eval.yaml` |
| `/templates` | Template browser (shared read-only library) |
| `/templates/[id]` | Template detail |
| `/queue` | Queue dashboard — running, queued, and recently finished jobs |

## Data flow

The Web UI never writes evaluation data directly. API routes translate HTTP requests into filesystem reads/writes inside `.micro-eval/`:

```
Browser → Next.js API route → .micro-eval/runs/<id>/*.json
                            ↘ .micro-eval/runs/<id>/evaluation.json  (writes)
```

Decisions are recomputed server-side after each human evaluation write. `localStorage` is **not** used for any evaluation state.

---

## Pages

### `/` — Run List

The landing page shows every run found under `.micro-eval/runs/`.

| Column | Description |
|---|---|
| Run ID | Unique identifier, links to run detail |
| Project | Project name from the run manifest |
| Status | `completed`, `failed`, `running` |
| Created | ISO timestamp of run start |
| Tasks | Number of tasks in the run |
| Configurations | Number of configurations evaluated |

Click any row to navigate to that run's detail page.

---

### `/run/[id]` — Run Detail

The primary analysis surface. Four panels are shown on a single page.

#### Decision Summary

A verdict badge at the top of the page shows the computed decision status:

| Badge | Meaning |
|---|---|
| `improved` | New configuration scores better on most tasks |
| `regressed` | New configuration scores worse |
| `mixed` | Split results across tasks |
| `inconclusive` | Not enough signal to distinguish |
| `not_comparable` | Run snapshots differ — baseline comparison is invalid |
| `needs_human_review` | Automatic scorer deferred; human annotation required |

A **confidence level** (low / medium / high) is shown alongside the badge, derived from score variance and repetition count.

#### Caveats Panel

If the run produced any caveats — mismatched isolation levels, missing Langfuse credentials, skipped LLM judge calls — they appear here as collapsible warnings.

::: warning Caveats affect comparability
A `not_comparable` decision is automatically issued when the `SameStartSnapshot` check detects differing workspace commits, fixture digests, or toolchain fingerprints between configurations.
:::

#### Result Matrix

A grid with **tasks as rows** and **configurations as columns**. Each cell is color-coded:

- Green — all expectations passed
- Red — one or more expectations failed
- Orange — execution error (timeout, non-zero exit without `exit_code` expectation, etc.)
- Grey — skipped or not run

**Click any cell** to open a detail drawer showing:

- Output summary (stdout/stderr excerpt)
- Evidence collected (expectation results, LLM judge score, human annotation)
- Artifact links

#### Human Evaluation Panel

Add a score and comment for any cell directly from the UI. Fields:

| Field | Type | Notes |
|---|---|---|
| Score | Number 0–1 | Appended to the cell's evidence list |
| Comment | Free text | Stored verbatim in `evaluation.json` |

Submitting triggers a server-side decision recomputation. The verdict badge updates on the next page load.

```json
// .micro-eval/runs/<id>/evaluation.json (example entry)
{
  "task_id": "write-tests",
  "configuration_id": "sonnet-4-5",
  "repetition": 0,
  "score": 0.9,
  "comment": "Output correct but formatting was inconsistent.",
  "annotated_at": "2026-06-15T10:42:00Z"
}
```

---

### `/run/[id]/review` — Review Surface

A deeper analysis page designed for post-run retrospectives. Added in Phase 2.

#### Matrix Heatmap

The same task × configuration grid rendered as a heatmap, with pass/fail coloring normalized across all cells. Useful for spotting which tasks are systematically hard across configurations.

#### Cost Panel

Per-configuration cost metrics aggregated from Langfuse trace data (when available):

- Total token spend (prompt + completion)
- Average cost per task
- Cost distribution chart across repetitions

::: tip Langfuse is optional
If `LANGFUSE_SECRET_KEY` is not set, the cost panel shows a "No trace data" placeholder. The rest of the review page remains fully functional.
:::

#### Trace Panel

Per-cell trace summaries: latency, tool call count, span tree depth. Click a summary to expand the full span list.

#### Evidence Viewer

Select any cell to browse its complete evidence chain:

1. Deterministic validator results (exit code, contains, file_exists, command)
2. LLM judge score and rationale (if run)
3. Human annotation (if added)

#### Aggregation Stats

Below the heatmap, a stats bar shows run-level aggregates:

| Metric | Description |
|---|---|
| `pass@k` | Pass rate across k repetitions per task-configuration pair |
| Median latency | Median wall-clock time per task execution |
| Total cost | Sum of Langfuse-reported token cost across all cells |

---

### `/run/[id]/artifact/[artifactId]` — Artifact Viewer

Renders a single artifact captured during a run.

#### Text artifacts

Rendered inline with syntax highlighting when the `media_type` is `text/*`. Long artifacts are paginated.

#### Metadata sidebar

| Field | Value |
|---|---|
| Kind | `stdout`, `file`, `diff`, `custom` |
| Size | Bytes |
| Media type | MIME type from the manifest |
| SHA-256 | Digest for integrity verification |

#### Boundary enforcement

Access is mediated by two checks:

1. The `artifact_id` must appear in the run's artifact manifest
2. The resolved file path must stay inside `.micro-eval/runs/<id>/`

::: danger Out-of-boundary requests are rejected
Any artifact URL that resolves outside the run directory returns HTTP 403. This prevents path traversal even if an artifact manifest entry is malformed.
:::

#### Oversized and binary artifacts

| Condition | Behaviour |
|---|---|
| `size > 1 MB` | Warning placeholder shown; raw content not sent to browser |
| `media_type` is binary | Warning placeholder; download link offered instead |
| Artifact missing from manifest | HTTP 404 |
| Path escapes run boundary | HTTP 403 |

---

## Configuration reference

The Web UI reads one environment variable at startup:

```bash
MICRO_EVAL_PROJECT_ROOT=/absolute/path/to/project
```

All `.micro-eval/` reads and writes are relative to this root. There is no other required configuration.

::: tip Secrets are never served
Environment variables matching `MICRO_EVAL_SECRET_*` are auto-redacted server-side and never included in API responses or rendered artifact content.
:::

---

## API routes (internal)

These routes are consumed by the Next.js pages. They are not a public API and may change between minor versions.

| Route | Method | Description |
|---|---|---|
| `/api/runs` | GET | List all run manifests |
| `/api/runs/[id]` | GET | Single run manifest + decision |
| `/api/runs/[id]/matrix` | GET | Full result matrix with evidence |
| `/api/runs/[id]/evaluate` | POST | Write human evaluation entry |
| `/api/runs/[id]/artifacts/[artifactId]` | GET | Serve artifact content |
| `/api/runs/[id]/traces` | GET | Aggregated trace data (Langfuse) |

---

## Troubleshooting

**Page shows "No runs found"**

Check that `MICRO_EVAL_PROJECT_ROOT` points to a directory containing `.micro-eval/runs/`. Run `micro-eval list` in your project to confirm runs exist.

**Decision badge stays `needs_human_review` after annotation**

Human evaluation triggers a recomputation on the next full page load. Hard-refresh (`Ctrl+Shift+R` / `Cmd+Shift+R`) the run detail page.

**Cost panel shows "No trace data"**

Langfuse credentials (`LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST`) were not set when the run executed. Cost data is captured at run time and cannot be backfilled.

**Artifact viewer returns 403**

The artifact manifest entry contains a path that resolves outside the run directory. This is a data integrity issue — re-run the evaluation to regenerate clean artifacts.
