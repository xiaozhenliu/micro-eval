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

    env = {
        **os.environ,
        "MICRO_EVAL_SERVER_MODE": "true",
        "MICRO_EVAL_DATA_ROOT": str(data_root),
    }

    typer.echo(f"Starting Next.js on {host}:{port}...")
    next_proc = None
    try:
        next_proc = subprocess.Popen(
            ["npx", "next", "start", "--port", str(port), "--hostname", host],
            cwd=ui_dir,
            env=env,
        )

        def shutdown(signum, frame):
            typer.echo("\nShutting down...")
            worker_proc.terminate()
            if next_proc:
                next_proc.terminate()
            worker_proc.wait(timeout=10)
            if next_proc:
                next_proc.wait(timeout=10)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        next_proc.wait()
    except KeyboardInterrupt:
        worker_proc.terminate()
        if next_proc:
            next_proc.terminate()
    finally:
        worker_proc.wait(timeout=10)


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
