"""Workspace management CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from micro_eval.server.workspace import WorkspaceError, WorkspaceManager

workspace_app = typer.Typer(name="workspace", help="Manage server workspaces.")


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


@workspace_app.command(name="create")
def workspace_create(
    name: str = typer.Option(..., "--name", help="Workspace name"),
    owner: str = typer.Option(..., "--owner", help="Owner identifier"),
    template: str | None = typer.Option(None, "--template", help="Template ID to copy from"),
    description: str = typer.Option("", "--description", help="Description"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Create a new workspace."""
    manager = WorkspaceManager(data_root)
    try:
        meta = manager.create(name=name, owner=owner, template_id=template, description=description)
    except WorkspaceError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(meta.model_dump_json(indent=2))


@workspace_app.command(name="list")
def workspace_list(
    all_ws: bool = typer.Option(False, "--all", help="Include archived workspaces"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """List workspaces."""
    manager = WorkspaceManager(data_root)
    for ws in manager.list_workspaces(include_archived=all_ws):
        typer.echo(f"{ws.workspace_id}  {ws.name}  owner={ws.owner}  status={ws.status}")


@workspace_app.command(name="update")
def workspace_update(
    workspace_id: str = typer.Argument(..., help="Workspace ID to update"),
    name: str | None = typer.Option(None, "--name", help="New workspace name"),
    description: str | None = typer.Option(None, "--description", help="New description"),
    status: str | None = typer.Option(None, "--status", help="New status (active|archived)"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Update workspace metadata."""
    manager = WorkspaceManager(data_root)
    fields = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if status is not None:
        fields["status"] = status
    if not fields:
        typer.echo("Error: no fields to update", err=True)
        raise typer.Exit(1)
    meta = manager.update(workspace_id, **fields)
    if meta is None:
        typer.echo(f"Error: workspace not found: {workspace_id}", err=True)
        raise typer.Exit(1)
    typer.echo(meta.model_dump_json(indent=2))


@workspace_app.command(name="delete")
def workspace_delete(
    workspace_id: str = typer.Argument(..., help="Workspace ID to delete"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
) -> None:
    """Delete a workspace (irreversible)."""
    from micro_eval.server.queue import QueueDB
    db_path = data_root / "queue.db"
    if db_path.exists():
        db = QueueDB(db_path)
        if db.has_pending_jobs(workspace_id):
            typer.echo("Error: workspace has pending/running jobs. Cancel them first.", err=True)
            db.close()
            raise typer.Exit(1)
        db.close()

    manager = WorkspaceManager(data_root)
    meta = manager.get(workspace_id)
    if meta is None:
        typer.echo(f"Error: workspace not found: {workspace_id}", err=True)
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete workspace '{meta.name}' ({workspace_id})? This cannot be undone.")
        if not confirm:
            raise typer.Abort()

    manager.delete(workspace_id)
    typer.echo(f"Deleted workspace {workspace_id}")
