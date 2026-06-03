"""Validate local micro-eval configuration without running agents."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from micro_eval.config.loader import ConfigError, load_config, load_task_paths
from micro_eval.config.planner import build_run_plan, plan_summary

console = Console()


def validate_command(
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to eval.yaml"),
    output_format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    """Validate eval.yaml, task files, and matrix expansion."""
    config_path = _resolve_config_path(config)
    try:
        project = load_config(config_path)
        tasks = load_task_paths(config_path, project)
        plan = build_run_plan(project, tasks, project_root=config_path.parent)
    except ConfigError as exc:
        _emit_error("config", str(exc), output_format)
        raise typer.Exit(1)
    except ValueError as exc:
        _emit_error("validation", str(exc), output_format)
        raise typer.Exit(1)

    diagnostics = {
        "config_path": str(config_path),
        "project_name": project.project_name,
        "tasks": [task.id for task in tasks],
        "configurations": [configuration.id for configuration in project.configurations],
        "warnings": project.migration_warnings + (plan.same_start_snapshot.caveats if plan.same_start_snapshot else []),
        "plan": plan_summary(plan),
    }
    if output_format == "json":
        typer.echo(json.dumps(diagnostics, indent=2))
        return

    console.print(f"[green]Config OK:[/green] {config_path}")
    table = Table(title="micro-eval validate")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Project", project.project_name)
    table.add_row("Tasks", ", ".join(task.id for task in tasks) or "none")
    table.add_row("Configurations", ", ".join(configuration.id for configuration in project.configurations))
    table.add_row("Cells", str(len(plan.cells)))
    table.add_row("Replay digest", plan.replay_canonical.digest if plan.replay_canonical else "missing")
    console.print(table)
    for warning in diagnostics["warnings"]:
        console.print(f"[yellow]Warning:[/yellow] {warning}")


def _resolve_config_path(config: Path | None) -> Path:
    if config is not None:
        return config
    env_path = os.environ.get("MICRO_EVAL_CONFIG")
    if env_path:
        return Path(env_path)
    return Path("eval.yaml")


def _emit_error(kind: str, message: str, output_format: str) -> None:
    payload = {
        "error": {
            "type": kind,
            "message": message,
            "hint": "Check eval.yaml configurations[], tasks paths, argv command lists, and workspace paths.",
        }
    }
    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2), err=True)
    else:
        console.print(f"[red]{kind} error:[/red] {message}")
        console.print("Hint: Check eval.yaml configurations[], tasks paths, argv command lists, and workspace paths.")
