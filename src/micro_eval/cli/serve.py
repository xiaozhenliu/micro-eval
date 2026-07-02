"""Server launch CLI commands."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import typer

from micro_eval.server.models import ServerConfig


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


def _terminate_proc(proc: subprocess.Popen, name: str, timeout: int = 5) -> None:
    """Terminate a subprocess, escalating to kill after timeout."""
    if proc.poll() is not None:
        return
    typer.echo(f"  Stopping {name}...")
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        typer.echo(f"  Force-killing {name}...")
        proc.kill()
        proc.wait(timeout=5)


def serve_command(
    port: int = typer.Option(3000, "--port", help="HTTP port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Start the Team Server (Next.js + worker)."""
    data_root = data_root.expanduser()
    data_root.mkdir(mode=0o700, parents=True, exist_ok=True)

    config_path = data_root / "server.json"
    if not config_path.exists():
        config = ServerConfig(bind_host=host, bind_port=port, data_root=str(data_root))
        config_path.write_text(config.model_dump_json(indent=2))
    else:
        config = ServerConfig.model_validate_json(config_path.read_text())

    from micro_eval.server.queue import QueueDB
    db = QueueDB(data_root / "queue.db")
    db.close()

    (data_root / "workspaces").mkdir(exist_ok=True)
    (data_root / "templates").mkdir(exist_ok=True)

    # Seed a demo template on first start so a fresh server has something to
    # run immediately. Only runs when the template registry is empty, so it
    # never clobbers templates an admin has already created or removed.
    from micro_eval.server.template import TemplateRegistry

    registry = TemplateRegistry(data_root)
    if not registry.list_templates():
        seed_dir = Path(__file__).resolve().parent.parent / "server" / "seed_template"
        if seed_dir.exists():
            try:
                registry.create(
                    source_dir=seed_dir,
                    template_id="demo-codefix",
                    name="Demo: Codefix Showdown (mock agents, free)",
                    description=(
                        "Deterministic mock agents for testing the evaluation "
                        "pipeline. Zero API cost."
                    ),
                    author="micro-eval",
                )
                typer.echo("Seeded demo template: demo-codefix")
            except Exception as exc:
                typer.echo(f"Warning: could not seed demo template: {exc}", err=True)

    typer.echo("Starting worker...")
    worker_proc = subprocess.Popen(
        [sys.executable, "-m", "micro_eval.cli.main", "worker", "--data-root", str(data_root)],
    )

    ui_dir = Path(__file__).resolve().parent.parent.parent.parent / "ui"
    if not ui_dir.exists():
        typer.echo(f"Error: ui/ directory not found at {ui_dir}", err=True)
        worker_proc.terminate()
        raise typer.Exit(1)

    next_dir = ui_dir / ".next"
    if not next_dir.exists():
        typer.echo("Building Next.js...")
        # Inject the same server env vars used by `next start` so build-time
        # rendering decisions (e.g. isServerMode() checks) match runtime.
        build_env = {
            **os.environ,
            "MICRO_EVAL_SERVER_MODE": "true",
            "MICRO_EVAL_DATA_ROOT": str(data_root),
        }
        build_result = subprocess.run(["npm", "run", "build"], cwd=ui_dir, env=build_env)
        if build_result.returncode != 0:
            typer.echo("Error: Next.js build failed", err=True)
            worker_proc.terminate()
            raise typer.Exit(1)
    else:
        # Warn (but don't auto-rebuild) if the existing build looks stale
        # relative to the UI sources, so startup stays predictable.
        build_id = next_dir / "BUILD_ID"
        if build_id.exists():
            build_mtime = build_id.stat().st_mtime
            ui_src = ui_dir / "src"
            if ui_src.exists():
                latest_src = max(
                    (p.stat().st_mtime for p in ui_src.rglob("*") if p.is_file()),
                    default=0,
                )
                if latest_src > build_mtime:
                    typer.echo(
                        "Warning: UI sources are newer than the last build. "
                        "Run 'cd ui && npm run build' to update.",
                        err=True,
                    )

    env = {
        **os.environ,
        "MICRO_EVAL_SERVER_MODE": "true",
        "MICRO_EVAL_DATA_ROOT": str(data_root),
    }

    typer.echo(f"Starting Next.js on {host}:{port}...")
    next_proc = None
    cleaned_up = False

    def cleanup() -> None:
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        typer.echo("\nShutting down...")
        if next_proc is not None:
            _terminate_proc(next_proc, "Next.js")
        _terminate_proc(worker_proc, "worker")

    def shutdown(signum, frame):
        cleanup()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        next_proc = subprocess.Popen(
            ["npx", "next", "start", "--port", str(port), "--hostname", host],
            cwd=ui_dir,
            env=env,
        )
        next_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


def worker_command(
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Start the run worker (standalone)."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_root = data_root.expanduser()
    config_path = data_root / "server.json"
    config = None
    if config_path.exists():
        config = ServerConfig.model_validate_json(config_path.read_text())

    from micro_eval.server.worker import run_worker
    run_worker(data_root, config)
