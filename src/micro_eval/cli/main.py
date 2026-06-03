"""micro-eval CLI entry point."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from micro_eval.cli.init import init_command
from micro_eval.cli.list import list_command
from micro_eval.cli.report import report_command
from micro_eval.cli.run import run_command
from micro_eval.cli.validate import validate_command

app = typer.Typer(
    name="micro-eval",
    help="Agent/Skill evaluation assistant for small AI teams.",
    no_args_is_help=True,
)

app.command(name="init")(init_command)
app.command(name="run")(run_command)
app.command(name="list")(list_command)
app.command(name="report")(report_command)
app.command(name="validate")(validate_command)


@app.command()
def ui(
    port: int = typer.Option(3000, help="Port for the UI server"),
) -> None:
    """Start the Next.js web UI (requires ui/ directory)."""
    ui_dir = Path.cwd() / "ui"
    if not ui_dir.exists():
        typer.echo("Error: ui/ directory not found.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Starting UI on port {port}...")
    try:
        subprocess.run(
            ["npm", "run", "dev", "--", "--port", str(port)],
            cwd=ui_dir,
            check=True,
        )
    except FileNotFoundError:
        typer.echo("Error: npm not found. Install Node.js first.", err=True)
        raise typer.Exit(1)
    except KeyboardInterrupt:
        typer.echo("\nUI stopped.")


if __name__ == "__main__":
    app()
