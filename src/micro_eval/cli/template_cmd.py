"""Template management CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from micro_eval.server.template import TemplateRegistry

template_app = typer.Typer(name="template", help="Manage evaluation templates.")


def _default_data_root() -> Path:
    return Path.home() / ".micro-eval-server"


@template_app.command(name="create")
def template_create(
    source_dir: Path = typer.Argument(..., help="Source directory to package as template"),
    template_id: str = typer.Option(..., "--id", help="Template ID"),
    name: str = typer.Option(..., "--name", help="Template name"),
    description: str = typer.Option("", "--description"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Create a template from a local directory."""
    registry = TemplateRegistry(data_root)
    meta = registry.create(source_dir, template_id=template_id, name=name, description=description)
    typer.echo(meta.model_dump_json(indent=2))


@template_app.command(name="update")
def template_update(
    template_id: str = typer.Argument(..., help="Template ID to update"),
    source_dir: Path = typer.Argument(..., help="New source directory"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Update a template with new content."""
    registry = TemplateRegistry(data_root)
    meta = registry.update(template_id, source_dir)
    typer.echo(meta.model_dump_json(indent=2))


@template_app.command(name="list")
def template_list(
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """List all templates."""
    registry = TemplateRegistry(data_root)
    for tpl in registry.list_templates():
        typer.echo(f"{tpl.template_id}  {tpl.name}  v{tpl.version}")


@template_app.command(name="delete")
def template_delete(
    template_id: str = typer.Argument(..., help="Template ID to delete"),
    data_root: Path = typer.Option(_default_data_root(), "--data-root"),
) -> None:
    """Delete a template."""
    registry = TemplateRegistry(data_root)
    if registry.delete(template_id):
        typer.echo(f"Deleted template {template_id}")
    else:
        typer.echo(f"Template not found: {template_id}", err=True)
        raise typer.Exit(1)
