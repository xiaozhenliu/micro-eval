"""Apply a human evaluation to a run cell via stdin JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from micro_eval.evaluation.human import build_human_evaluation
from micro_eval.store.run_store import RunStore


def apply_evaluation_command(
    run_id: str = typer.Option(..., "--run-id", help="Run ID"),
    cell_id: str = typer.Option(..., "--cell-id", help="Cell ID"),
) -> None:
    """Apply a human evaluation and recompute the run decision.

    Reads a JSON payload from stdin with fields: pass_fail, score, scores,
    comment, evaluator.  Writes {evaluation, evidence, decision} JSON to stdout.
    """
    project_root = Path.cwd()
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        typer.echo(f"Invalid JSON on stdin: {exc}", err=True)
        raise typer.Exit(1)

    evaluation, evidence = build_human_evaluation(
        cell_id=cell_id,
        pass_fail=payload.get("pass_fail"),
        score=payload.get("score"),
        scores=payload.get("scores"),
        comment=payload.get("comment", ""),
        evaluator=payload.get("evaluator", "human"),
    )
    store = RunStore(project_root)
    try:
        record = store.append_evaluation(
            run_id=run_id,
            cell_id=cell_id,
            evaluation=evaluation,
            evidence=evidence,
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    result = {
        "evaluation": evaluation.model_dump(mode="json"),
        "evidence": evidence.model_dump(mode="json"),
        "decision": record.decision.model_dump(mode="json") if record.decision else None,
    }
    sys.stdout.write(json.dumps(result))
