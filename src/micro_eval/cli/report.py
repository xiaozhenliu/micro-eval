"""Report command for canonical and legacy runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from jinja2 import Environment, select_autoescape
from rich.console import Console
from rich.table import Table

from micro_eval.models.run import RunRecord
from micro_eval.models.schema import Run
from micro_eval.store.run_store import RunStore

console = Console()

REPORT_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>micro-eval Report: {{ run_id }}</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; }
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
<h1>micro-eval Report</h1>
<p class="meta">Run ID: {{ run_id }}</p>
<p><strong>Decision:</strong> {{ decision }}</p>
{% if caveats %}
<h2>Caveats</h2>
<ul>{% for caveat in caveats %}<li>{{ caveat }}</li>{% endfor %}</ul>
{% endif %}
{% if stats %}
<h2>Basic Honest Stats</h2>
<table>
<tr><th>Configuration</th><th>Pass rate</th><th>pass@k</th><th>Mean latency</th><th>Median latency</th><th>Cost</th></tr>
{% for s in stats %}
<tr><td>{{ s.configuration }}</td><td>{{ s.pass_rate }}</td><td>{{ s.pass_at_k }}</td><td>{{ s.mean_latency }}</td><td>{{ s.median_latency }}</td><td>{{ s.cost }}</td></tr>
{% endfor %}
</table>
{% endif %}
<h2>Results</h2>
<table>
<tr><th>Task</th><th>Configuration</th><th>Status</th><th>Score</th><th>Latency</th></tr>
{% for r in results %}
<tr>
<td>{{ r.task }}</td><td>{{ r.configuration }}</td><td class="{{ r.status }}">{{ r.status }}</td><td>{{ r.score }}</td><td>{{ r.latency }}</td>
</tr>
{% endfor %}
</table>
{% if artifacts %}
<h2>Artifacts</h2>
<table>
<tr><th>Artifact ID</th><th>Kind</th><th>Path</th><th>Size</th><th>Warning</th></tr>
{% for artifact in artifacts %}
<tr><td><code>{{ artifact.artifact_id }}</code></td><td>{{ artifact.kind }}</td><td>{{ artifact.path }}</td><td>{{ artifact.size_bytes }}</td><td>{{ artifact.warning }}</td></tr>
{% endfor %}
</table>
{% endif %}
</body>
</html>
"""


def report_command(
    run_file: Path | None = typer.Argument(None, help="Legacy run JSON or canonical run.json path"),
    run_id: str | None = typer.Option(None, "--run", help="Canonical run id; latest if omitted and no run file"),
    output_format: str = typer.Option("html", "--format", help="text, json, or html"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output HTML path"),
) -> None:
    """Generate a report from a run result."""
    data = _load_run_data(run_file, run_id)
    if output_format == "json":
        typer.echo(json.dumps(data, indent=2))
        return
    if output_format == "text":
        _print_text_report(data)
        return
    html = _render_html_report(data)
    if output is None:
        output = Path(f"{data['id']}.html")
    output.write_text(html)
    console.print(f"[green]Report generated:[/green] {output}")


def _load_run_data(run_file: Path | None, run_id: str | None) -> dict[str, Any]:
    if run_file is not None:
        if not run_file.exists():
            console.print(f"[red]Run file not found:[/red] {run_file}")
            raise typer.Exit(1)
        raw = json.loads(run_file.read_text())
        return _normalize_run_data(raw, run_file=run_file)
    store = RunStore(Path.cwd())
    selected = run_id or store.latest_run_id()
    if selected is None:
        console.print("[red]No runs found.[/red]")
        raise typer.Exit(1)
    try:
        record = store.read_run(selected)
    except Exception as exc:
        console.print(f"[red]Failed to load run:[/red] {exc}")
        raise typer.Exit(1)
    return record.model_dump(mode="json")


def _render_html_report(data: dict[str, Any]) -> str:
    """Render the static HTML report with HTML autoescape enabled."""
    return Environment(autoescape=select_autoescape(["html", "xml"])).from_string(REPORT_TEMPLATE).render(
        **_template_context(data)
    )


def _normalize_run_data(raw: dict[str, Any], run_file: Path | None = None) -> dict[str, Any]:
    if "cells" in raw and "project_name" in raw:
        record = RunRecord.model_validate(raw)
        if run_file is not None:
            decision_path = run_file.parent / "decision.json"
            if decision_path.exists():
                from micro_eval.models.decision import DecisionReport

                record.decision = DecisionReport.model_validate_json(decision_path.read_text())
        return record.model_dump(mode="json")
    legacy = Run(**raw)
    return legacy.model_dump(mode="json")


def _print_text_report(data: dict[str, Any]) -> None:
    console.print(f"[bold]Run:[/bold] {data['id']}")
    decision = data.get("decision") or {}
    if decision:
        console.print(f"[bold]Decision:[/bold] {decision.get('verdict')} ({decision.get('confidence')})")
    table = Table(title="Result Matrix")
    table.add_column("Task")
    table.add_column("Configuration")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Latency")
    for row in _result_rows(data):
        table.add_row(row["task"], row["configuration"], row["status"], row["score"], row["latency"])
    console.print(table)
    caveats = decision.get("caveats", []) if decision else []
    for caveat in caveats:
        console.print(f"[yellow]Caveat:[/yellow] {caveat}")
    aggregation = decision.get("aggregation", {}) if decision else {}
    if aggregation:
        stats = Table(title="Basic Honest Stats")
        stats.add_column("Configuration")
        stats.add_column("Pass rate")
        stats.add_column("pass@k")
        stats.add_column("Mean latency")
        stats.add_column("Median latency")
        stats.add_column("Cost")
        for config_id, row in _aggregation_items(aggregation):
            stats.add_row(
                str(config_id),
                _format_optional_rate(row.get("pass_rate")),
                _format_pass_at_k(row.get("pass_at_k")),
                _format_optional_ms(row.get("mean_latency_ms")),
                _format_optional_ms(row.get("median_latency_ms")),
                _format_cost(row),
            )
        console.print(stats)


def _template_context(data: dict[str, Any]) -> dict[str, Any]:
    decision = data.get("decision") or {}
    return {
        "run_id": data["id"],
        "decision": decision.get("verdict", "inconclusive"),
        "caveats": decision.get("caveats", []),
        "stats": _stats_rows(decision.get("aggregation", {})),
        "results": _result_rows(data),
        "artifacts": data.get("artifacts", []),
    }


def _result_rows(data: dict[str, Any]) -> list[dict[str, str]]:
    if "results" not in data:
        return []
    rows = []
    for result in data["results"]:
        rows.append(
            {
                "task": str(result.get("task_id", "")),
                "configuration": str(result.get("configuration_id") or result.get("agent_name", "")),
                "status": str(result.get("status", "")),
                "score": "-" if result.get("score") is None else f"{float(result['score']):.2f}",
                "latency": f"{float(result.get('latency_s', 0.0)):.2f}s",
            }
        )
    return rows


def _format_optional_seconds(value: Any) -> str:
    return "-" if value is None else f"{float(value):.2f}s"


def _format_optional_ms(value: Any) -> str:
    return "-" if value is None else f"{float(value) / 1000.0:.2f}s"


def _format_optional_rate(value: Any) -> str:
    return "-" if value is None else f"{float(value) * 100:.0f}%"


def _format_pass_at_k(value: Any) -> str:
    if not value:
        return "-"
    items = sorted((int(k), float(v)) for k, v in value.items())
    if len(items) == 1 and items[0][0] == 1:
        return "-"
    return ", ".join(f"@{k}={v * 100:.0f}%" for k, v in items)


def _format_cost(row: dict[str, Any]) -> str:
    cost = row.get("total_cost")
    if isinstance(cost, dict):
        amount = cost.get("amount")
        source = cost.get("source", "unknown")
        return f"unavailable ({source})" if amount is None else f"${float(amount):.4f} ({source})"
    if row.get("cost_usd") is not None:
        return f"${float(row['cost_usd']):.4f}"
    return "-"


def _aggregation_items(aggregation: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    per_config = aggregation.get("per_configuration") if isinstance(aggregation, dict) else None
    source = per_config if isinstance(per_config, dict) else aggregation
    return [(str(config_id), row) for config_id, row in source.items() if isinstance(row, dict)]


def _stats_rows(aggregation: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for config_id, row in _aggregation_items(aggregation):
        rows.append(
            {
                "configuration": str(config_id),
                "pass_rate": _format_optional_rate(row.get("pass_rate")),
                "pass_at_k": _format_pass_at_k(row.get("pass_at_k")),
                "mean_latency": _format_optional_ms(row.get("mean_latency_ms")),
                "median_latency": _format_optional_ms(row.get("median_latency_ms")),
                "cost": _format_cost(row),
            }
        )
    return rows
