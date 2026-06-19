# Team Server

micro-eval's Team Server turns a single machine into a shared evaluation server for your team. Members access it through a browser, create isolated workspaces, and enqueue runs — while the server handles execution serially to prevent resource contention.

::: tip When to use server mode
Use `micro-eval serve` when your team (1–20 people) wants to:
- Share evaluation results without copying files between machines
- Use a common template library for consistent eval configurations
- Enqueue runs from a browser instead of SSH-ing into a machine
- Track who ran what (attribution records)
:::

::: warning Intranet only
The server has no authentication. Do not expose it to the public internet. All team members are trusted to self-report accurate identities.
:::

## Architecture

The server runs as two cooperating processes on a single machine:

- **Next.js server** — serves the browser UI and REST API, handles workspace and template management, and writes run jobs to the queue
- **Python worker** — reads from the queue and executes runs using `ExecutionKernel`, the same engine used by `micro-eval ui`

```
Browser → Next.js Server → queue.db ← Python Worker → ExecutionKernel
                ↕                              ↕
        ~/.micro-eval-server/workspaces/<ws-id>/.micro-eval/runs/
```

The queue database (`queue.db`) is a SQLite file in WAL mode. The Python worker processes one run at a time. Cells within a single run still respect the `max_concurrency` setting from the workspace's `eval.yaml`.

Both processes are started by a single command and share the same data root directory. The Next.js server does not call the Python worker directly — communication happens entirely through the queue database.

## Getting Started

```bash
# Start the team server on the default port
micro-eval serve

# Specify a port
micro-eval serve --port 3000

# Use a custom data directory (useful for mounted volumes or CI machines)
micro-eval serve --data-root /data/eval-server --port 8080
```

On first start, `micro-eval serve` creates the data root directory and initialises its structure:

```
~/.micro-eval-server/
├── server.json        ← server config (port, data root, created_at)
├── queue.db           ← SQLite WAL queue
├── worker.pid         ← Python worker PID (absent when worker is stopped)
├── workspaces/        ← one directory per workspace
└── templates/         ← read-only template registry
```

To stop the server, send `SIGINT` (Ctrl-C). The Next.js process will exit immediately; the Python worker finishes the current run cell before stopping, so no run data is lost.

## Workspaces

A **workspace** is an isolated directory under `~/.micro-eval-server/workspaces/<ws-id>/`. It acts as a `project_root` for `ExecutionKernel` — it has its own `eval.yaml`, `.micro-eval/runs/`, and `tasks/` directory, completely independent from every other workspace.

Members create workspaces from the browser or CLI. Each workspace is owned by the member who created it, but any member can enqueue runs against any workspace.

### Lifecycle

| State | Meaning |
|-------|---------|
| `active` | Normal state. Runs can be enqueued. |
| `archived` | Read-only. Run history is preserved; no new runs can be enqueued. |
| `deleted` | Scheduled for removal. Cannot be deleted while it has pending queue jobs. |

### CLI management

```bash
# Create a workspace (optionally from a template)
micro-eval workspace create --name "agent-comparison-q3" --template baseline-eval

# List all workspaces
micro-eval workspace list

# Archive a workspace (preserves run history, prevents new runs)
micro-eval workspace update <ws-id> --status archived

# Delete a workspace (fails if it has pending queue jobs)
micro-eval workspace delete <ws-id>
```

### Physical layout

```
~/.micro-eval-server/workspaces/<ws-id>/
├── workspace.json     ← metadata (name, owner, status, created_at)
├── eval.yaml          ← evaluation configuration
├── tasks/             ← task YAML files
└── .micro-eval/
    └── runs/          ← run JSON files (source of truth)
```

## Templates

A **template** is a read-only snapshot in `~/.micro-eval-server/templates/`. Templates capture a known-good `eval.yaml` plus any associated task files so that new workspaces start from a consistent baseline.

When a member creates a workspace from a template, micro-eval **copies** the template's contents into the new workspace directory. The workspace is immediately independent — later changes to the template do not affect existing workspaces, and changes in a workspace do not affect the template.

Templates are managed via CLI only, not through the browser.

```bash
# Register a directory as a template
micro-eval template create --name baseline-eval --source ./my-eval-config/

# List available templates
micro-eval template list

# Update a template (does not affect existing workspaces)
micro-eval template update baseline-eval --source ./my-eval-config-v2/

# Remove a template (does not affect existing workspaces)
micro-eval template delete baseline-eval
```

::: tip Template updates are not propagated
Updating a template has no effect on workspaces already created from it. If you want existing workspaces to pick up new task files, copy them into each workspace manually or create new workspaces from the updated template.
:::

## Run Queue

Runs are enqueued from the browser (or CLI) and executed serially by the Python worker. This prevents the machine from being overloaded when multiple members submit runs simultaneously.

### Job statuses

| Status | Meaning |
|--------|---------|
| `queued` | Waiting for the worker to pick it up |
| `running` | Currently executing in `ExecutionKernel` |
| `done` | Completed successfully |
| `failed` | Terminated with an error |
| `cancelled` | Cancelled before or during execution |

### Enqueueing a run

From the browser, navigate to a workspace and click **Run**. The UI shows a live queue position and progress indicator while the job is `queued` or `running`. The page polls the server for status updates — no WebSocket connection is required.

From the CLI:

```bash
micro-eval queue submit --workspace <ws-id>
```

### Cancellation semantics

- **Queued jobs** are cancelled immediately — the record is removed from the queue before the worker ever touches it.
- **Running jobs** receive a cancellation signal after the current run cell finishes. The worker does not kill a cell mid-execution; it stops before starting the next cell. Completed cells are preserved in the run result.

### Crash recovery

If the Python worker crashes while a job is `running`, the worker marks the job as `failed` with a `worker_crash` error on the next startup. No run data from completed cells is lost — the partial result is written to `.micro-eval/runs/` as usual.

## Member Identity

The server uses a self-reported identity for attribution. Members send their identity in the `X-Micro-Eval-Member` HTTP header with every write request.

### Format

- 1–64 characters
- Allowed characters: `[a-zA-Z0-9._-]`
- Examples: `alice`, `bob.smith`, `team-lead`

### When it is used

| Operation | Header required? |
|-----------|-----------------|
| GET requests (read-only) | No — defaults to `anonymous` |
| Create workspace | Yes |
| Submit run | Yes |
| Cancel run | Yes |
| Create / update template | Yes |

The member name is stored in the workspace metadata and in the run result as `submitted_by`. It appears in the UI on run history and workspace details pages.

::: warning Identity is self-reported, not verified
Any member can claim any name. The header exists for attribution and audit trails — not for access control. If a member claims the wrong identity, they can attribute runs incorrectly, but they cannot gain any capabilities they would not otherwise have.
:::

## Security Model

The server is designed for a trusted intranet environment. Its security model has four layers:

### CSRF protection

All state-changing endpoints require:

1. **`Content-Type: application/json`** — plain HTML form submissions (a common CSRF vector) are rejected
2. **`X-Micro-Eval-Member` custom header** — browsers block cross-origin requests from setting custom headers without CORS permission
3. **No permissive CORS headers** — the server does not respond with `Access-Control-Allow-Origin: *`
4. **`Host` header allowlist** — requests from unexpected `Host` values are rejected

### `config_overrides` whitelist

Members can submit `config_overrides` when enqueueing a run to change a subset of configuration parameters (e.g., `max_concurrency`, `timeout_s`). The server enforces a strict whitelist of overridable fields. Fields that could affect workspace boundaries, provider selection, or secrets handling are not overridable.

### Path traversal protection

All workspace and template paths are resolved and validated inside the data root before any file operation. A path that resolves outside `~/.micro-eval-server/` is rejected with a `400` error.

### Workspace isolation

Each workspace directory is self-contained. `ExecutionKernel` receives the workspace path as `project_root` and cannot read or write outside it during a run. This is the same isolation guarantee as `micro-eval ui` running against a local `project_root`.

For guidance on OS-level and VM-level sandboxing within runs, see [Workspace & Sandboxing](/guide/workspace-isolation).

## Data Directory

```
~/.micro-eval-server/
├── server.json            ← { port, data_root, created_at, version }
├── queue.db               ← SQLite WAL database
│   └── (tables: jobs, job_events)
├── worker.pid             ← Python worker PID file
├── workspaces/
│   ├── <ws-id-1>/
│   │   ├── workspace.json
│   │   ├── eval.yaml
│   │   ├── tasks/
│   │   └── .micro-eval/runs/
│   └── <ws-id-2>/
│       └── ...
└── templates/
    ├── baseline-eval/
    │   ├── template.json
    │   ├── eval.yaml
    │   └── tasks/
    └── ...
```

The JSON run files under `.micro-eval/runs/` are the authoritative source of truth — identical to those produced by `micro-eval ui`. The SQLite queue and index are derived and can be rebuilt from the JSON files.

## Comparison with Local Mode

| Aspect | `micro-eval ui` | `micro-eval serve` |
|--------|-----------------|-------------------|
| Who runs it | One person on their laptop | Shared machine for the whole team |
| Data location | `<project_root>/.micro-eval/` | `~/.micro-eval-server/workspaces/<ws-id>/` |
| Browser access | `localhost` only | Any machine on the network |
| Run execution | Triggered by CLI or browser locally | Enqueued from browser, executed by background worker |
| Concurrency | Runs immediately | Serial queue (one run at a time) |
| Workspaces | One per project root | Multiple named workspaces per server |
| Templates | N/A | Read-only shared library |
| Identity | N/A | Self-reported via `X-Micro-Eval-Member` |
| Authentication | None (local only) | None (intranet trust model) |

## Next Steps

- [Workspace & Sandboxing](/guide/workspace-isolation) — isolation levels, trust levels, and network policies for agent execution
- [Security Model](/guide/security) — full security reference, including secrets handling and path validation
- [CLI Commands](/reference/cli) — complete reference for `micro-eval serve`, `workspace`, `template`, and `queue` subcommands
