"""build-plan CLI command — construct RunPlan from eval.yaml without executing."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from micro_eval.config.loader import ConfigError, config_error_hint
from micro_eval.config.planner import build_workspace_plan


def build_plan_command(
    workspace: Path = typer.Option(..., "--workspace", help="Path to workspace directory"),
    overrides: str | None = typer.Option(None, "--overrides", help="JSON string of config overrides"),
    strict_paths: bool = typer.Option(
        False,
        "--strict-paths",
        help=(
            "Treat the workspace directory as the trust boundary: eval.yaml and task files "
            "are opened without following symlinks and task references may not leave it."
        ),
    ),
) -> None:
    """Construct a RunPlan from eval.yaml and output JSON to stdout."""
    override_dict = {}
    if overrides:
        override_dict = json.loads(overrides)

    ALLOWED_OVERRIDES = {"max_concurrency"}
    for key in override_dict:
        if key not in ALLOWED_OVERRIDES:
            typer.echo(json.dumps({"error": f"override '{key}' not allowed. Allowed: {ALLOWED_OVERRIDES}"}), err=True)
            raise typer.Exit(1)

    max_concurrency = override_dict.get("max_concurrency")

    try:
        plan = build_workspace_plan(workspace, strict_paths=strict_paths, max_concurrency=max_concurrency)
    except ConfigError as exc:
        hint = config_error_hint(exc)
        payload = {"error": str(exc)}
        if hint:
            payload["hint"] = hint
        typer.echo(json.dumps(payload), err=True)
        raise typer.Exit(1)
    typer.echo(plan.model_dump_json(indent=2))
