"""Run command - executes evaluation runs."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from micro_eval.config.loader import ConfigError, load_config, load_task_paths
from micro_eval.config.planner import build_run_plan, plan_summary
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.run import CellStatus

console = Console()


def run_command(
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to eval.yaml"),
    parallel: bool | None = typer.Option(None, "--parallel/--no-parallel", help="Legacy parallel flag"),
    max_concurrency: int | None = typer.Option(None, "--max-concurrency", help="Maximum concurrent cells"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print RunPlan without launching agents"),
    output_format: str = typer.Option("text", "--format", help="text or json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Execute a canonical evaluation run."""
    config_path = _resolve_config_path(config)
    try:
        project = load_config(config_path)
        tasks = load_task_paths(config_path, project)
    except ConfigError as exc:
        _error("Config error", str(exc), output_format)
        raise typer.Exit(1)

    if not tasks:
        _error("Tasks error", "No tasks found", output_format)
        raise typer.Exit(1)

    concurrency = max_concurrency
    if concurrency is None and parallel is not None:
        concurrency = project.guardrails.max_concurrency if parallel else 1
    try:
        plan = build_run_plan(project, tasks, max_concurrency=concurrency, project_root=config_path.parent)
    except ValueError as exc:
        _error("Plan error", str(exc), output_format)
        raise typer.Exit(1)

    if dry_run:
        if output_format == "json":
            typer.echo(plan.model_dump_json(indent=2))
        else:
            console.print_json(data=plan_summary(plan))
        return

    if output_format != "json":
        console.print(f"[bold]Running evaluation:[/bold] {plan.project_name}")
        console.print(f"  Run: {plan.run_id}")
        console.print(f"  Cells: {len(plan.cells)} | Max concurrency: {plan.guardrails.max_concurrency}")
        if verbose and plan.migration_warnings:
            for warning in plan.migration_warnings:
                console.print(f"[yellow]Migration warning:[/yellow] {warning}")

    kernel = ExecutionKernel(project_root=config_path.parent)
    record = asyncio.run(kernel.run(plan))

    if output_format == "json":
        typer.echo(record.model_dump_json(indent=2))
        return

    console.print(f"\n[green]Results saved:[/green] {config_path.parent / record.output_dir / record.id / 'run.json'}")
    table = Table(title="Results Summary")
    table.add_column("Task")
    table.add_column("Configuration")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Latency")
    for result in record.results:
        status_color = {
            CellStatus.passed: "green",
            CellStatus.failed: "red",
            CellStatus.error: "red",
            CellStatus.timeout: "yellow",
        }.get(result.status, "white")
        table.add_row(
            result.task_id,
            result.configuration_id,
            f"[{status_color}]{result.status.value}[/{status_color}]",
            f"{result.score:.2f}" if result.score is not None else "-",
            f"{result.latency_s:.2f}s",
        )
    console.print(table)
    if record.decision:
        console.print(f"Decision: [bold]{record.decision.verdict.value}[/bold] ({record.decision.confidence})")


def _error(kind: str, message: str, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps({"error": {"type": kind, "message": message}}, indent=2), err=True)
    else:
        console.print(f"[red]{kind}:[/red] {message}")


def _resolve_config_path(config: Path | None) -> Path:
    if config is not None:
        return config
    env_path = os.environ.get("MICRO_EVAL_CONFIG")
    if env_path:
        return Path(env_path)
    return Path("eval.yaml")
