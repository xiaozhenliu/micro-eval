# Team Server Quickstart Example

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `team-server-quickstart` example that demonstrates the full Team Server workflow — `micro-eval serve`, template management, workspace creation, queue operations, and member attribution — in a self-contained, scriptable walkthrough.

**Architecture:** Unlike other examples that use `micro-eval run` (CLI mode), this example showcases server mode. A shell script (`walkthrough.sh`) drives the flow step by step: start the server, create a template from a bundled eval directory, create a workspace from that template, enqueue a run via the HTTP API, observe queue status, and inspect results. A companion `run.py` provides the standard Python entrypoint for the runner framework. The example bundles a minimal eval config (one mock agent, one task) to keep it self-contained.

**Tech Stack:** Python 3.11+, micro-eval CLI (serve/template/workspace/queue subcommands), curl (HTTP API), Next.js (server UI)

## Global Constraints

- The example must work without external API keys or LLM providers
- Must use deterministic mock agents (zero cost)
- The `run.py` should orchestrate the full walkthrough programmatically (no shell script dependency)
- Server processes must be cleaned up reliably (no zombie processes)
- Must demonstrate member attribution via `X-Micro-Eval-Member` header
- Data root must be local to the example directory (not `~/.micro-eval-server`)

---

### Task 1: Create the example directory and bundled eval content

**Files:**
- Create: `examples/team-server-quickstart/eval-template/eval.yaml`
- Create: `examples/team-server-quickstart/eval-template/tasks/smoke-task.yaml`
- Create: `examples/team-server-quickstart/eval-template/workspace/scripts/mock-agent.py`

**Interfaces:**
- Consumes: Nothing
- Produces: A directory (`eval-template/`) that can be registered as a server template. Contains eval.yaml + one task + one mock agent script.

- [ ] **Step 1: Create eval-template/eval.yaml**

```yaml
project_name: team-server-smoke
description: Minimal smoke eval for team server quickstart.

configurations:
  - id: mock-fixer
    name: "Mock Fixer"
    role: baseline
    repetitions: 1
    agent:
      name: mock-fixer
      command: ["{python}", "workspace/scripts/mock-agent.py", "{output_file}"]
      input_mode: stdin
      output_mode: file
      timeout_s: 30
      env: {}
      required_secrets: []

tasks_dir: tasks
output_dir: .micro-eval/runs

guardrails:
  max_concurrency: 1
  timeout_s: 60
  stop_on_cell_error: false

evaluation:
  comparison_subject: "mock fixer for server smoke test"
  success_criteria:
    - The mock agent writes the expected output and exits cleanly.
  required_evaluators: [validator]
  denominator_policy: include_failed

trace:
  enabled: true
  provider: process

judge:
  enabled: false
```

- [ ] **Step 2: Create eval-template/tasks/smoke-task.yaml**

```yaml
id: smoke-task
name: "Smoke test task"
description: "Trivial task that any mock agent can pass."
input_payload: |
  Write the word "DONE" to the output file.
expectations:
  - type: contains
    stream: output
    value: "DONE"
workspace:
  type: files
  files:
    - workspace
rubric: "The agent should write DONE to the output."
business_impact_tier: 3
tags: [smoke, team-server]
```

- [ ] **Step 3: Create eval-template/workspace/scripts/mock-agent.py**

```python
#!/usr/bin/env python3
"""Deterministic mock agent for team server quickstart."""
import sys

output_file = sys.argv[1] if len(sys.argv) > 1 else None

# Read input from stdin (consumed but not used by mock)
task_input = sys.stdin.read()

result = "DONE"

if output_file:
    with open(output_file, "w") as f:
        f.write(result)
else:
    print(result)
```

- [ ] **Step 4: Commit**

```bash
git add examples/team-server-quickstart/eval-template/
git commit -m "feat(examples): add team-server-quickstart eval template content"
```

---

### Task 2: Create run.py that orchestrates the full server walkthrough

**Files:**
- Create: `examples/team-server-quickstart/run.py`

**Interfaces:**
- Consumes: `eval-template/` directory (Task 1)
- Produces: A runnable script that starts the server, creates template + workspace, enqueues a run, waits for completion, and prints results. Follows the runner pattern for CLI flags but internally uses server-mode APIs.

- [ ] **Step 1: Write run.py**

```python
#!/usr/bin/env python3
"""Team Server quickstart walkthrough.

Demonstrates the complete Team Server workflow:
  1. Start `micro-eval serve` with a local data root
  2. Create a template from a bundled eval directory
  3. Create a workspace from that template
  4. Enqueue a run via the HTTP API with member attribution
  5. Monitor queue status until completion
  6. Inspect results

Usage:
    python examples/team-server-quickstart/run.py
    python examples/team-server-quickstart/run.py --port 3001
    python examples/team-server-quickstart/run.py --skip-run   # skip server start, show commands only

Prerequisites:
    cd ui && npm run build   # Next.js must be built once before serve mode works
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen

EXAMPLE_NAME = "team-server-quickstart"
MEMBER_NAME = "quickstart-user"
POLL_INTERVAL = 2.0
MAX_WAIT = 120


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    example_root = Path(__file__).resolve().parent
    data_root = example_root / ".server-data"
    template_source = example_root / "eval-template"
    command_prefix = micro_eval_command(repo_root)

    if command_prefix is None:
        print(
            "Could not find a runnable micro-eval CLI.",
            file=sys.stderr,
            flush=True,
        )
        return 2

    if args.skip_run:
        print_walkthrough_commands(args.port, data_root, template_source, command_prefix)
        return 0

    # Clean up previous data root
    if data_root.exists():
        shutil.rmtree(data_root)

    base_url = f"http://127.0.0.1:{args.port}"
    server_proc = None

    def cleanup():
        if server_proc and server_proc.poll() is None:
            print("\n==> Stopping server...", flush=True)
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()
                server_proc.wait(timeout=5)

    atexit.register(cleanup)

    # Step 1: Start server
    print("=" * 60, flush=True)
    print("Team Server Quickstart Walkthrough", flush=True)
    print("=" * 60, flush=True)

    print("\n==> Step 1: Starting micro-eval serve...", flush=True)
    server_proc = subprocess.Popen(
        [
            *command_prefix,
            "serve",
            "--port", str(args.port),
            "--host", "127.0.0.1",
            "--data-root", str(data_root),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if not wait_for_server(base_url, timeout=60):
        print("Error: server did not start within 60 seconds.", file=sys.stderr, flush=True)
        return 1
    print(f"    Server running at {base_url}", flush=True)

    # Step 2: Create template
    print("\n==> Step 2: Creating template from eval-template/...", flush=True)
    run_step(
        "template create",
        [
            *command_prefix,
            "template", "create",
            str(template_source),
            "--id", "quickstart-smoke",
            "--name", "Quickstart Smoke Template",
            "--description", "Minimal template for the team server quickstart",
            "--data-root", str(data_root),
        ],
        cwd=example_root,
    )

    # Step 3: List templates
    print("\n==> Step 3: Listing templates...", flush=True)
    run_step(
        "template list",
        [*command_prefix, "template", "list", "--data-root", str(data_root)],
        cwd=example_root,
    )

    # Step 4: Create workspace from template
    print("\n==> Step 4: Creating workspace from template...", flush=True)
    result = subprocess.run(
        [
            *command_prefix,
            "workspace", "create",
            "--name", "quickstart-workspace",
            "--owner", MEMBER_NAME,
            "--template", "quickstart-smoke",
            "--description", "Workspace for team server quickstart demo",
            "--data-root", str(data_root),
        ],
        cwd=example_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error creating workspace: {result.stderr}", file=sys.stderr, flush=True)
        return 1
    workspace_meta = json.loads(result.stdout)
    workspace_id = workspace_meta["workspace_id"]
    print(f"    Created workspace: {workspace_id}", flush=True)

    # Step 5: List workspaces
    print("\n==> Step 5: Listing workspaces...", flush=True)
    run_step(
        "workspace list",
        [*command_prefix, "workspace", "list", "--data-root", str(data_root)],
        cwd=example_root,
    )

    # Step 6: Enqueue a run via HTTP API with member attribution
    print("\n==> Step 6: Enqueueing run via HTTP API...", flush=True)
    print(f"    Member attribution: {MEMBER_NAME}", flush=True)
    enqueue_body = json.dumps({"workspace_id": workspace_id}).encode()
    req = Request(
        f"{base_url}/api/evaluate",
        data=enqueue_body,
        headers={
            "Content-Type": "application/json",
            "X-Micro-Eval-Member": MEMBER_NAME,
            "X-Micro-Eval-Request": "true",
        },
        method="POST",
    )
    try:
        resp = urlopen(req)
        enqueue_result = json.loads(resp.read())
        job_id = enqueue_result.get("job_id", "(unknown)")
        print(f"    Enqueued job: {job_id}", flush=True)
    except Exception as exc:
        print(f"Error enqueueing: {exc}", file=sys.stderr, flush=True)
        return 1

    # Step 7: Poll queue status until completion
    print("\n==> Step 7: Monitoring queue status...", flush=True)
    run_step(
        "queue status",
        [*command_prefix, "queue", "status", "--data-root", str(data_root)],
        cwd=example_root,
    )

    elapsed = 0.0
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        status_result = subprocess.run(
            [*command_prefix, "queue", "status", "--data-root", str(data_root)],
            capture_output=True,
            text=True,
        )
        if "Running: (none)" in status_result.stdout and "Queued: (none)" in status_result.stdout:
            print(f"    Run completed after ~{elapsed:.0f}s", flush=True)
            break
    else:
        print(f"Warning: timed out after {MAX_WAIT}s", file=sys.stderr, flush=True)

    # Step 8: Show results
    print("\n==> Step 8: Checking results...", flush=True)
    ws_dir = data_root / "workspaces" / workspace_id
    runs_dir = ws_dir / ".micro-eval" / "runs"
    if runs_dir.exists():
        run_dirs = sorted(runs_dir.iterdir())
        if run_dirs:
            latest = run_dirs[-1]
            run_json = latest / "run.json"
            if run_json.exists():
                run_data = json.loads(run_json.read_text())
                print(f"    Run ID: {run_data.get('run_id', '?')}", flush=True)
                print(f"    Owner: {run_data.get('owner', '?')}", flush=True)
                cells = run_data.get("cells", [])
                for cell in cells:
                    print(
                        f"    Cell {cell.get('cell_id', '?')}: "
                        f"status={cell.get('status', '?')}",
                        flush=True,
                    )

    # Summary
    print("\n" + "=" * 60, flush=True)
    print("Walkthrough complete!", flush=True)
    print("=" * 60, flush=True)
    print(f"""
What you just saw:
  1. micro-eval serve — started the Team Server (Next.js + worker)
  2. template create  — packaged eval-template/ as a reusable template
  3. workspace create — instantiated a workspace from that template
  4. HTTP API         — enqueued a run with member attribution header
  5. queue status     — monitored the serial queue until completion
  6. Results          — inspected run.json with owner attribution

Key concepts:
  - Templates are read-only blueprints; workspaces are mutable copies
  - The serial queue ensures only one run executes at a time
  - Member attribution (X-Micro-Eval-Member) tracks who triggered each run
  - Data root ({data_root}) contains all server state

To explore in the browser: python examples/{EXAMPLE_NAME}/run.py --ui
To clean up: rm -rf {data_root}
""", flush=True)

    if args.ui:
        print("==> Server still running — open browser to explore", flush=True)
        print(f"    {base_url}", flush=True)
        print("    Press Ctrl+C to stop.", flush=True)
        try:
            server_proc.wait()
        except KeyboardInterrupt:
            pass
    else:
        cleanup()

    return 0


def wait_for_server(base_url: str, timeout: float = 60) -> bool:
    """Poll the server until it responds or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urlopen(f"{base_url}/api/health", timeout=2)
            return True
        except (URLError, OSError):
            time.sleep(1)
    return False


def print_walkthrough_commands(port: int, data_root: Path, template_source: Path, prefix: list[str]) -> None:
    """Print the manual walkthrough commands without executing."""
    cmd = " ".join(prefix)
    print(f"""
Team Server Quickstart — Manual Commands
=========================================

# 1. Start the server
{cmd} serve --port {port} --host 127.0.0.1 --data-root {data_root}

# 2. Create a template
{cmd} template create {template_source} --id quickstart-smoke \\
    --name "Quickstart Smoke Template" --data-root {data_root}

# 3. List templates
{cmd} template list --data-root {data_root}

# 4. Create a workspace
{cmd} workspace create --name quickstart-workspace --owner {MEMBER_NAME} \\
    --template quickstart-smoke --data-root {data_root}

# 5. List workspaces
{cmd} workspace list --data-root {data_root}

# 6. Enqueue a run (replace WS_ID with actual workspace ID)
curl -X POST http://127.0.0.1:{port}/api/evaluate \\
    -H "Content-Type: application/json" \\
    -H "X-Micro-Eval-Member: {MEMBER_NAME}" \\
    -H "X-Micro-Eval-Request: true" \\
    -d '{{"workspace_id": "WS_ID"}}'

# 7. Check queue status
{cmd} queue status --data-root {data_root}
""", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run the {EXAMPLE_NAME} walkthrough.")
    parser.add_argument("--skip-run", action="store_true", help="Print commands without executing.")
    parser.add_argument("--max-concurrency", type=int, default=1, help="(Unused in server mode, kept for runner compatibility)")
    parser.add_argument("--ui", action="store_true", help="Keep server running for browser exploration.")
    parser.add_argument("--port", type=int, default=3001, help="Server port (default: 3001 to avoid conflicts).")
    return parser.parse_args()


def micro_eval_command(repo_root: Path) -> list[str] | None:
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--project", str(repo_root), "micro-eval"]
    installed_cli = shutil.which("micro-eval")
    if installed_cli:
        return [installed_cli]
    src_dir = repo_root / "src"
    if src_dir.exists():
        return [sys.executable, "-m", "micro_eval.cli.main"]
    return None


def run_step(
    label: str,
    command: Sequence[str],
    *,
    cwd: Path,
    env_overlay: dict[str, str] | None = None,
) -> None:
    env = os.environ.copy()
    if command[:3] == [sys.executable, "-m", "micro_eval.cli.main"]:
        src_dir = Path(__file__).resolve().parents[2] / "src"
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    if env_overlay:
        env.update(env_overlay)
    result = subprocess.run(list(command), cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        print(f"    Step '{label}' exited with code {result.returncode}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Test with --skip-run to verify it prints the walkthrough**

Run: `python examples/team-server-quickstart/run.py --skip-run`
Expected: prints the manual command walkthrough without starting anything

- [ ] **Step 3: Commit**

```bash
git add examples/team-server-quickstart/run.py
git commit -m "feat(examples): add team-server-quickstart run.py walkthrough"
```

---

### Task 3: Register in run-example.py and add README

**Files:**
- Modify: `examples/run-example.py:17-22` (ALL_EXAMPLES list)
- Modify: `examples/run-example.py` parse_args choices
- Create: `examples/team-server-quickstart/README.md`
- Modify: `examples/README.md` (add row to table, update coverage matrix)

**Interfaces:**
- Consumes: run.py from Task 2, eval-template from Task 1
- Produces: Example registered in runner, documented in README

- [ ] **Step 1: Add to ALL_EXAMPLES and choices in run-example.py**

In `examples/run-example.py`, add `"team-server-quickstart"` to `ALL_EXAMPLES` and to the argparse choices list.

- [ ] **Step 2: Write README.md**

```markdown
# Team Server Quickstart

End-to-end walkthrough of the Team Server (`micro-eval serve`) workflow.

## What it demonstrates

- **`micro-eval serve`** — starts the Team Server (Next.js UI + run worker)
- **Template management** — `template create` / `template list` to package
  and register reusable evaluation blueprints
- **Workspace management** — `workspace create` from a template, `workspace list`
- **HTTP API** — enqueue a run via `POST /api/evaluate` with `Content-Type`
  and `X-Micro-Eval-Request` headers (CSRF protection)
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
   and `X-Micro-Eval-Request: true` headers. Without these, the server rejects
   the request.

5. **Data root isolation** — all server state lives in `.server-data/` under
   the example directory, not in `~/.micro-eval-server`.

## Cleanup

```bash
rm -rf examples/team-server-quickstart/.server-data
```
```

- [ ] **Step 3: Update examples/README.md**

Add a row to the "Available use cases" table:

```markdown
| [Team Server Quickstart](team-server-quickstart/) | End-to-end `micro-eval serve` workflow: template management, workspace creation from template, HTTP API run enqueue with member attribution, serial queue monitoring, and result inspection. Uses a deterministic mock agent. Requires `cd ui && npm run build` once. |
```

Add rows to the coverage matrix:

```markdown
| `micro-eval serve` | | | | | ✓ |
| Template management | | | | | ✓ |
| Workspace management | | | | | ✓ |
| HTTP API (evaluate) | | | | | ✓ |
| Member attribution | | | | | ✓ |
| Serial queue | | | | | ✓ |
| CSRF protection | | | | | ✓ |
```

- [ ] **Step 4: Commit**

```bash
git add examples/run-example.py examples/team-server-quickstart/README.md examples/README.md
git commit -m "docs(examples): add team-server-quickstart README, register in runner"
```

---

### Task 4: Add .gitignore for server data

**Files:**
- Create: `examples/team-server-quickstart/.gitignore`

**Interfaces:**
- Consumes: Nothing
- Produces: Prevents `.server-data/` from being committed

- [ ] **Step 1: Create .gitignore**

```
.server-data/
```

- [ ] **Step 2: Commit**

```bash
git add examples/team-server-quickstart/.gitignore
git commit -m "chore(examples): gitignore team-server-quickstart server data"
```
