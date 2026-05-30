"""Report command - generates HTML comparison reports."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from jinja2 import Template
from rich.console import Console

from micro_eval.models.schema import Run

console = Console()

REPORT_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>micro-eval Report: {{ run.id }}</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 900px;
       margin: 2rem auto; padding: 0 1rem; }
h1 { color: #1a1a2e; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
th { background: #f5f5f5; }
.pass { color: #16a34a; font-weight: bold; }
.fail, .error { color: #dc2626; font-weight: bold; }
.timeout { color: #ca8a04; font-weight: bold; }
.meta { color: #666; font-size: 0.9rem; }
</style>
</head>
<body>
<h1>Evaluation Report</h1>
<p class="meta">Run ID: {{ run.id }} | {{ run.timestamp }}</p>
<p><strong>Baseline:</strong> {{ run.baseline_agent }} |
   <strong>Candidate:</strong> {{ run.candidate_agent }}</p>
<p>Execution: {{ run.execution_order }} |
   Tasks: {{ run.tasks | length }}</p>

<h2>Results</h2>
<table>
<tr><th>Task</th><th>Agent</th><th>Status</th>
    <th>Score</th><th>Latency</th></tr>
{% for r in run.results %}
<tr>
  <td>{{ r.task_id }}</td>
  <td>{{ r.agent_name }}</td>
  <td class="{{ r.status }}">{{ r.status }}</td>
  <td>{{ "%.2f"|format(r.score) if r.score is not none else "-" }}</td>
  <td>{{ "%.2f"|format(r.latency_s) }}s</td>
</tr>
{% endfor %}
</table>
</body>
</html>
"""


def report_command(
    run_file: Path = typer.Argument(..., help="Path to run JSON file"),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output HTML path"
    ),
) -> None:
    """Generate an HTML report from a run result."""
    if not run_file.exists():
        console.print(f"[red]Run file not found:[/red] {run_file}")
        raise typer.Exit(1)

    try:
        data = json.loads(run_file.read_text())
        run = Run(**data)
    except (json.JSONDecodeError, Exception) as e:
        console.print(f"[red]Failed to parse run file:[/red] {e}")
        raise typer.Exit(1)

    template = Template(REPORT_TEMPLATE)
    html = template.render(run=run)

    if output is None:
        output = run_file.with_suffix(".html")

    output.write_text(html)
    console.print(f"[green]Report generated:[/green] {output}")
