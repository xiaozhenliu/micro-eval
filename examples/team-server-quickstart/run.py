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
    enqueue_body = b"{}"
    req = Request(
        f"{base_url}/api/workspaces/{workspace_id}/runs/enqueue",
        data=enqueue_body,
        headers={
            "Content-Type": "application/json",
            "X-Micro-Eval-Member": MEMBER_NAME,
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
                owner = run_data.get("owner")
                context = run_data.get("server_context") or {}
                results = run_data.get("results", [])
                if owner != MEMBER_NAME:
                    print(
                        f"Error: run.json owner was {owner!r}, expected {MEMBER_NAME!r}.",
                        file=sys.stderr,
                        flush=True,
                    )
                    return 1
                if context.get("workspace_id") != workspace_id or context.get("job_id") != job_id:
                    print(
                        "Error: run.json server_context does not match the enqueued job.",
                        file=sys.stderr,
                        flush=True,
                    )
                    return 1
                if not results or any(cr.get("status") != "pass" for cr in results):
                    print("Error: Team Server smoke run did not produce all pass cells.", file=sys.stderr, flush=True)
                    return 1
                print(f"    Run ID: {run_data.get('id', '?')}", flush=True)
                print(f"    Owner: {owner}", flush=True)
                for cr in results:
                    print(
                        f"    Cell {cr.get('cell_id', '?')}: "
                        f"status={cr.get('status', '?')}",
                        flush=True,
                    )
            else:
                print("Error: completed workspace has no run.json.", file=sys.stderr, flush=True)
                return 1
        else:
            print("Error: completed workspace has no run directories.", file=sys.stderr, flush=True)
            return 1
    else:
        print("Error: completed workspace has no runs directory.", file=sys.stderr, flush=True)
        return 1

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
            urlopen(f"{base_url}/api/server/status", timeout=2)
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
curl -X POST http://127.0.0.1:{port}/api/workspaces/WS_ID/runs/enqueue \\
    -H "Content-Type: application/json" \\
    -H "X-Micro-Eval-Member: {MEMBER_NAME}" \\
    -d '{{}}'

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
