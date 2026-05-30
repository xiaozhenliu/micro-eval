"""Run command - executes evaluation runs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from micro_eval.config.loader import load_config, load_tasks, ConfigError
from micro_eval.engine.runner import AgentRunner
from micro_eval.engine.scorer import Scorer
from micro_eval.models.schema import TaskStatus

console = Console()


def run_command(
    config: Path = typer.Option(
        Path("eval.yaml"), "--config", "-c", help="Path to eval.yaml"
    ),
    parallel: bool = typer.Option(True, help="Run agents in parallel"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Execute an evaluation run comparing baseline vs candidate."""
    try:
        project = load_config(config)
    except ConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1)

    # Load tasks
    tasks_dir = config.parent / project.tasks_dir
    try:
        tasks = load_tasks(tasks_dir)
    except ConfigError as e:
        console.print(f"[red]Tasks error:[/red] {e}")
        raise typer.Exit(1)

    if not tasks:
        console.print("[yellow]No tasks found.[/yellow]")
        raise typer.Exit(1)

    console.print(
        f"[bold]Running evaluation:[/bold] {project.project_name}"
    )
    console.print(
        f"  Baseline: {project.baseline.name} | "
        f"Candidate: {project.candidate.name}"
    )
    console.print(f"  Tasks: {len(tasks)} | Parallel: {parallel}")

    # Execute
    runner = AgentRunner(work_dir=config.parent)
    run_result = asyncio.run(
        runner.run_eval(
            baseline=project.baseline,
            candidate=project.candidate,
            tasks=tasks,
            parallel=parallel,
        )
    )

    # Score results
    scorer = Scorer()
    for result in run_result.results:
        task = next((t for t in tasks if t.id == result.task_id), None)
        if task:
            result.score = scorer.score(result, task)
            result.status = scorer.judge_pass_fail(result, task)

    # Save results
    output_dir = config.parent / project.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{run_result.id}.json"
    output_file.write_text(
        run_result.model_dump_json(indent=2)
    )
    console.print(f"\n[green]Results saved:[/green] {output_file}")

    # Print summary table
    table = Table(title="Results Summary")
    table.add_column("Task")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Latency")

    for result in run_result.results:
        status_color = {
            TaskStatus.passed: "green",
            TaskStatus.failed: "red",
            TaskStatus.error: "red",
            TaskStatus.timeout: "yellow",
        }.get(result.status, "white")

        table.add_row(
            result.task_id,
            result.agent_name,
            f"[{status_color}]{result.status.value}[/{status_color}]",
            f"{result.score:.2f}" if result.score is not None else "-",
            f"{result.latency_s:.2f}s",
        )

    console.print(table)
