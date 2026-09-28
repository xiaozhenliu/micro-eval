# Team Server Quickstart

End-to-end walkthrough of the Team Server (`micro-eval serve`) workflow.

## What it demonstrates

- **`micro-eval serve`** — starts the Team Server (Next.js UI + run worker)
- **Template management** — `template create` / `template list` to package
  and register reusable evaluation blueprints
- **Workspace management** — `workspace create` from a template, `workspace list`
- **HTTP API** — enqueue a run via `POST /api/workspaces/{id}/runs/enqueue`
  with `Content-Type: application/json` header (CSRF protection)
- **Member attribution** — `X-Micro-Eval-Member` header tracks who triggered each run
- **Serial queue** — `queue status` shows the SQLite-backed FIFO queue
- **Worker** — background worker polls the queue and executes runs

## Prerequisites

```bash
# Next.js UI must be built once before serve mode works
cd ui && npm run build
```

No external API keys required — uses a deterministic mock agent.

## Quick start

```bash
# Automated walkthrough (starts server, runs all steps, shuts down)
python examples/team-server-quickstart/run.py

# Keep server running for browser exploration after walkthrough
python examples/team-server-quickstart/run.py --ui

# Print manual commands without executing
python examples/team-server-quickstart/run.py --skip-run
```

## Files

| File | Purpose |
|---|---|
| `run.py` | Orchestrates the full walkthrough programmatically |
| `eval-template/eval.yaml` | Minimal eval config bundled as template content |
| `eval-template/tasks/smoke-task.yaml` | Single mock task |
| `eval-template/workspace/scripts/mock-agent.py` | Deterministic mock agent |

## What to observe

1. **Template → Workspace flow** — templates are read-only blueprints stored in
   `data-root/templates/`. Workspaces are mutable copies in `data-root/workspaces/`.

2. **Serial queue** — the queue guarantees only one run executes at a time.
   `queue status` shows the running job and any queued jobs.

3. **Member attribution** — `run.json` contains `owner: quickstart-user`,
   recording who triggered the run.

4. **CSRF protection** — the HTTP API requires `Content-Type: application/json`
   and a valid `X-Micro-Eval-Member` header. Without these, the server rejects
   the request.

5. **Data root isolation** — all server state lives in `.server-data/` under
   the example directory, not in `~/.micro-eval-server`.

## Cleanup

```bash
rm -rf examples/team-server-quickstart/.server-data
```
