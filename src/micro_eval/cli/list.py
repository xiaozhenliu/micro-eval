"""List local micro-eval runs."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from micro_eval.models.run import RunRecord
from micro_eval.store.run_store import RunStore

console = Console()


def list_command(
    output_dir: str = typer.Option(".micro-eval/runs", "--output-dir", help="Runs directory"),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """List run IDs sorted newest first."""
    store = RunStore(Path.cwd())
    runs = store.list_runs(output_dir)
    if output_format == "json":
        payload = [item.model_dump(mode="json") if isinstance(item, RunRecord) else item for item in runs]
        typer.echo(json.dumps(payload, indent=2))
        return
    if not runs:
        console.print("[yellow]No runs found.[/yellow]")
        return
    table = Table(title="micro-eval runs")
    table.add_column("Run ID")
    table.add_column("Status")
    table.add_column("Created")
    table.add_column("Cells")
    for item in runs:
        if isinstance(item, RunRecord):
            table.add_row(item.id, item.status.value, item.created_at, f"{len(item.results)}/{len(item.cells)}")
        else:
            table.add_row(str(item.get("id", "unknown")), "legacy", str(item.get("timestamp", "")), str(len(item.get("results", []))))
    console.print(table)
