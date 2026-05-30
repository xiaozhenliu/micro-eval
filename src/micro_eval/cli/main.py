"""micro-eval CLI entry point."""

import typer

from micro_eval.cli.run import run_command
from micro_eval.cli.report import report_command

app = typer.Typer(
    name="micro-eval",
    help="Agent/Skill evaluation assistant for small AI teams.",
    no_args_is_help=True,
)

app.command(name="run")(run_command)
app.command(name="report")(report_command)


@app.command()
def ui(
    port: int = typer.Option(3000, help="Port for the UI server"),
) -> None:
    """Start the Next.js web UI (requires ui/ directory)."""
    import subprocess
    import sys
    from pathlib import Path

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
