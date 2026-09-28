"""build-plan CLI command — construct RunPlan from eval.yaml without executing."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from micro_eval.config.loader import ConfigError, load_config, load_task_paths
from micro_eval.config.planner import build_run_plan


def build_plan_command(
    workspace: Path = typer.Option(..., "--workspace", help="Path to workspace directory"),
    overrides: str | None = typer.Option(None, "--overrides", help="JSON string of config overrides"),
) -> None:
    """Construct a RunPlan from eval.yaml and output JSON to stdout."""
    config_path = workspace / "eval.yaml"
    if not config_path.exists():
        typer.echo(json.dumps({"error": f"eval.yaml not found in {workspace}"}), err=True)
        raise typer.Exit(1)

    try:
        project = load_config(config_path)
        tasks = load_task_paths(config_path, project)
    except ConfigError as exc:
        typer.echo(json.dumps({"error": str(exc)}), err=True)
        raise typer.Exit(1)

    if not tasks:
        typer.echo(json.dumps({"error": "no tasks found"}), err=True)
        raise typer.Exit(1)

    override_dict = {}
    if overrides:
        override_dict = json.loads(overrides)

    ALLOWED_OVERRIDES = {"max_concurrency"}
    for key in override_dict:
        if key not in ALLOWED_OVERRIDES:
            typer.echo(json.dumps({"error": f"override '{key}' not allowed. Allowed: {ALLOWED_OVERRIDES}"}), err=True)
            raise typer.Exit(1)

    max_concurrency = override_dict.get("max_concurrency")

    plan = build_run_plan(project, tasks, max_concurrency=max_concurrency, project_root=workspace)
    typer.echo(plan.model_dump_json(indent=2))
