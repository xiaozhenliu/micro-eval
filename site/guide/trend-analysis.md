# Trend Analysis

Track how configurations perform across multiple runs over time. Trend analysis lets you answer questions like "did my last prompt change improve pass rates?" or "has agent latency drifted since we upgraded the underlying model?"

## How It Works

micro-eval keeps JSON run files as the **authoritative source of truth**. A derived index sits alongside the JSON store and enables fast time-series queries without duplicating data.

```
.micro-eval/
├── runs/
│   ├── run_20260610_143022.json   ← source of truth
│   ├── run_20260611_090155.json
│   └── run_20260614_171843.json
└── index.db                       ← derived, re-buildable from JSON
```

The index is updated automatically after each run completes. Existing JSON runs from before v0.3.0 can be imported in one command:

```bash
uv run micro-eval index import-json
```

## Drift-Aware Breakpoints

A **configuration digest** is a hash of the fields that define how a configuration actually executes: `command`, `params`, `repetitions`, and `skills_profile`. The digest is stored alongside each run entry in the index.

When you reuse a configuration id across runs but change its content — for example, pointing it at a new agent command or adjusting its timeout — the digest changes. micro-eval records a **drift breakpoint** between the two runs:

```
Run 1 (2026-06-10)  Run 2 (2026-06-11)  ⚡ DRIFT  Run 3 (2026-06-14)  Run 4 (2026-06-15)
[digest: a3f9...]   [digest: a3f9...]             [digest: c1d7...]   [digest: c1d7...]
                                          ↑
                              config.command changed
```

::: warning Do not draw conclusions across breakpoints
Results before and after a drift breakpoint belong to different configurations — even if the id is the same. Comparing pass rates across a breakpoint is as misleading as comparing two different agents. The trend chart annotates breakpoints visually so you can see exactly where the discontinuity is.
:::

### What Triggers a Breakpoint

| Field changed | Breakpoint recorded? |
|---------------|---------------------|
| `command` | Yes |
| `params` | Yes |
| `repetitions` | Yes |
| `skills_profile` | Yes |
| `description` (label only) | No |
| `environment` variables | No |

## Querying Trends via the API

The Next.js local UI exposes a `/api/trends` route that the trend chart page consumes. You can also query it directly for scripting or debugging.

**Required parameter:** `config_id` — the configuration id you want to inspect.

```bash
curl "http://localhost:3000/api/trends?config_id=my-agent"
```

**Example response:**

```json
{
  "config_id": "my-agent",
  "series": [
    {
      "run_id": "run_20260610_143022",
      "timestamp": "2026-06-10T14:30:22Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.72,
      "p50_latency_ms": 4200,
      "p95_latency_ms": 9800,
      "total_cost_usd": 0.031,
      "breakpoint_after": false
    },
    {
      "run_id": "run_20260611_090155",
      "timestamp": "2026-06-11T09:01:55Z",
      "digest": "a3f9c2b1",
      "pass_rate": 0.75,
      "p50_latency_ms": 4100,
      "p95_latency_ms": 9500,
      "total_cost_usd": 0.029,
      "breakpoint_after": true
    },
    {
      "run_id": "run_20260614_171843",
      "timestamp": "2026-06-14T17:18:43Z",
      "digest": "c1d7a412",
      "pass_rate": 0.81,
      "p50_latency_ms": 3700,
      "p95_latency_ms": 8200,
      "total_cost_usd": 0.027,
      "breakpoint_after": false
    }
  ],
  "breakpoints": [
    {
      "after_run_id": "run_20260611_090155",
      "reason": "digest changed: a3f9c2b1 → c1d7a412",
      "timestamp": "2026-06-14T17:18:43Z"
    }
  ]
}
```

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `config_id` | *(required)* | The configuration id to query |
| `since` | *(all runs)* | ISO-8601 timestamp; exclude runs before this date |
| `limit` | `50` | Maximum number of runs to return |

```bash
# Last 10 runs since June 1
curl "http://localhost:3000/api/trends?config_id=my-agent&since=2026-06-01T00:00:00Z&limit=10"
```

## Viewing Trends in the UI

Start the local UI and open the **Trends** tab:

```bash
uv run micro-eval ui
# opens http://localhost:3000
```

The trend chart shows:
- **Pass rate** over time (primary y-axis)
- **P50 / P95 latency** as a secondary series
- **Cost per run** as a bar series
- **Drift breakpoints** as vertical dashed lines with a tooltip explaining the digest change

Hover any data point to see the run id, timestamp, and task breakdown. Click a data point to navigate directly to that run's result matrix.

## Use Cases

### Regression Detection After a Prompt Change

You update your agent's system prompt and want to confirm it didn't break existing tasks:

```bash
# Run your eval suite before and after the change, using the same config id
uv run micro-eval run --config eval.yaml

# Edit your prompt, then run again
uv run micro-eval run --config eval.yaml

# Open trends to compare the two consecutive data points
uv run micro-eval ui
```

If `breakpoint_after` is `false` for both runs (same digest), you can directly compare pass rates and latencies.

### Monitoring Agent Performance Over Time

Schedule your eval suite nightly in CI and send results to the local store:

```yaml
# .github/workflows/nightly-eval.yml
name: Nightly Eval
on:
  schedule:
    - cron: '0 2 * * *'
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install uv && uv sync
      - run: uv run micro-eval run --config eval.yaml
      - uses: actions/upload-artifact@v4
        with:
          name: eval-results-${{ github.run_id }}
          path: .micro-eval/runs/
```

Download artifacts locally and import them:

```bash
# Unzip artifacts into .micro-eval/runs/, then rebuild the index
uv run micro-eval index import-json
uv run micro-eval ui
```

### Detecting Infrastructure Impact

When you upgrade a model provider, change sandbox configuration, or switch isolation levels, the configuration digest may change — producing a drift breakpoint. Use this as a signal to run a larger repetition set on both sides of the breakpoint to confirm whether any pass rate difference is statistically meaningful.

::: tip Configuration digest covers execution, not infrastructure
Changing your OS sandbox from `os_policy` (Seatbelt) to `logical` (git worktree) does not change the configuration digest, because `isolation_level` is not part of the digest. Only fields that directly affect what the agent receives and does are digested. If you want to compare isolation levels, use separate configuration ids.
:::

## Rebuilding the Index

The SQLite index is fully derived from JSON. If it becomes corrupted or out of sync, delete and rebuild it:

```bash
# Remove the stale index
rm .micro-eval/index.db

# Rebuild from all JSON runs in the store
uv run micro-eval index import-json
```

::: warning index.db is not a backup
Never treat `index.db` as a source of truth. Always keep the JSON run files. If you delete JSON runs, those data points are gone from the trend history permanently.
:::

## Next Steps

- [Security](./security) — how secrets are redacted and workspace boundaries are enforced
