"""Queue management CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

queue_app = typer.Typer(name="queue", help="Manage the run queue.")


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


@queue_app.command(name="status")
def queue_status(
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Show queue status."""
    from micro_eval.server.queue import QueueDB
    db = QueueDB(data_root.expanduser() / "queue.db")
    dashboard = db.get_queue_dashboard()
    if dashboard["running"]:
        r = dashboard["running"]
        typer.echo(f"Running: {r['job_id']}  workspace={r['workspace_id']}  owner={r['owner']}")
    else:
        typer.echo("Running: (none)")
    if dashboard["queued"]:
        typer.echo(f"Queued: {len(dashboard['queued'])} jobs")
        for q in dashboard["queued"]:
            typer.echo(f"  #{q['position']}: {q['job_id']}  workspace={q['workspace_id']}  owner={q['owner']}")
    else:
        typer.echo("Queued: (none)")
    db.close()


@queue_app.command(name="cancel")
def queue_cancel(
    job_id: str = typer.Argument(..., help="Job ID to cancel"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Cancel a queued or running job."""
    from micro_eval.server.queue import QueueDB
    db = QueueDB(data_root.expanduser() / "queue.db")
    try:
        result = db.request_cancel(job_id, "cli-admin")
        if result is None:
            typer.echo(f"Job not found: {job_id}", err=True)
            raise typer.Exit(1)
        if "error" in result:
            typer.echo(f"Cannot cancel: {result['error']} (status={result['status']})", err=True)
            raise typer.Exit(1)
        typer.echo(f"Job {job_id} → {result['status']}")
    finally:
        db.close()
