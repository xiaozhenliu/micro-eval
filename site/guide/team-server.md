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

::: tip Build freshness check
If a Next.js build already exists under `ui/.next`, `micro-eval serve` compares its `BUILD_ID` timestamp against the UI source files. If any source file is newer than the build, it prints a warning to stderr:

```
Warning: UI sources are newer than the last build. Run 'cd ui && npm run build' to update.
```

This is non-blocking — the server still starts with the existing (stale) build. If no build exists at all, `micro-eval serve` builds it automatically before starting and fails hard if that build fails.
:::

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
micro-eval workspace create --name "agent-comparison-q3" --owner alice --template baseline-eval

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
micro-eval template create ./my-eval-config --id baseline-eval --name "Baseline Eval"

# List available templates
micro-eval template list

# Update a template (does not affect existing workspaces)
micro-eval template update baseline-eval ./my-eval-config-v2

# Remove a template (does not affect existing workspaces)
micro-eval template delete baseline-eval
```

::: tip Template updates are not propagated
Updating a template has no effect on workspaces already created from it. If you want existing workspaces to pick up new task files, copy them into each workspace manually or create new workspaces from the updated template.
:::

### Demo template

On first start with an empty template registry, `micro-eval serve` automatically seeds a demo template named `demo-codefix` ("Demo: Codefix Showdown (mock agents, free)"). It only seeds when the registry has zero templates, so it never overwrites or duplicates templates an admin has already created.

The demo template uses a deterministic mock agent (a plain Python script, no LLM calls) to fix a rounding bug in a small ledger function — a self-contained task that runs end to end with **zero API cost**. It's meant as a working example: create a workspace from `demo-codefix` and enqueue a run to see the whole pipeline (workspace → queue → `ExecutionKernel` → results) without needing any API keys or spending any money.

## Run Queue

Runs are enqueued from the browser and executed serially by the Python worker. This prevents the machine from being overloaded when multiple members submit runs simultaneously.

### Job statuses

| Status | Meaning |
|--------|---------|
| `queued` | Waiting for the worker to pick it up |
| `running` | Currently executing in `ExecutionKernel` |
| `done` | Completed successfully |
| `failed` | Terminated with an error |
| `cancelled` | Cancelled before or during execution |

### Enqueueing a run

Runs are enqueued from the browser only — there is no CLI equivalent. Navigate to a workspace and click **Enqueue Run**. If you haven't set your member name yet (see [Member Identity](#member-identity)), the UI asks for it first.

Before the run is actually submitted, a confirmation card ("Run Preview") shows what is about to be enqueued:

- The cell count as `{tasks} task(s) × {configurations} config(s) × {repetitions} rep(s) = {total} cell(s)`
- The agent commands that will be executed

Review the preview and click **Confirm & Enqueue** to submit, or **Cancel** to back out without enqueueing anything. If the preview data can't be loaded, the card still lets you proceed — it shows a note that you can enqueue without a preview.

Once submitted, the UI shows a live queue position and progress indicator while the job is `queued` or `running`. The page polls the server for status updates — no WebSocket connection is required.

The CLI's `queue` subcommand only supports read/administrative operations — checking status and cancelling jobs (see [Cancellation semantics](#cancellation-semantics)) — not submitting new runs.

### Cancellation semantics

- **Queued jobs** are cancelled immediately — the record is removed from the queue before the worker ever touches it.
- **Running jobs** receive a cancellation signal after the current run cell finishes. The worker does not kill a cell mid-execution; it stops before starting the next cell. Completed cells are preserved in the run result.

### Crash recovery

If the Python worker crashes while a job is `running`, the worker marks the job as `failed` with a `worker_crash` error on the next startup. No run data from completed cells is lost — the partial result is written to `.micro-eval/runs/` as usual.

## Member Identity

The server uses a self-reported identity for attribution. Members send their identity in the `X-Micro-Eval-Member` HTTP header with every write request.

### Identity widget

The browser UI shows a persistent identity widget in the navigation bar, next to the Workspaces / Queue / Templates links. Before you set a name it reads "Set your name"; clicking it switches to an inline edit field where you can type a name and save it. The name is stored in the browser's `localStorage` and reused automatically on future visits — there's no server-side account or login.

This stored name is what the UI sends as the `X-Micro-Eval-Member` header for every write request (creating a workspace, enqueueing or cancelling a run, creating or updating a template). If you haven't set a name yet, actions that require one (like enqueueing a run) will prompt you for it first.

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
