"""Canonical run store for local JSON data."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from micro_eval.models.run import CellResult, RunPlan, RunRecord, RunStatus
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.ids import safe_path_segment
from micro_eval.decision.summary import build_decision


class RunStoreError(Exception):
    """Raised when run store operations fail."""


class RunStore:
    """Read and write canonical .micro-eval/runs data."""

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root)

    def run_dir(self, run_id: str, output_dir: str = ".micro-eval/runs") -> Path:
        """Return the canonical run directory."""
        root = self.project_root.resolve()
        path = (root / output_dir / run_id).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise RunStoreError("output_dir must stay inside the project root") from exc
        return path

    def init_run(self, plan: RunPlan) -> RunRecord:
        """Create run directory and initial run.json."""
        run_dir = self.run_dir(plan.run_id, plan.output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        record = RunRecord(
            id=plan.run_id,
            project_name=plan.project_name,
            status=RunStatus.running,
            created_at=plan.created_at,
            output_dir=plan.output_dir,
            config_hash=plan.config_hash,
            tasks=sorted({cell.task.id for cell in plan.cells}),
            configurations=sorted({cell.configuration.id for cell in plan.cells}),
            cells=[cell.cell_id for cell in plan.cells],
            migration_warnings=plan.migration_warnings,
            same_start_snapshot=plan.same_start_snapshot,
            replay_canonical=plan.replay_canonical,
        )
        self.write_run(record)
        return record

    def write_run(self, record: RunRecord) -> None:
        """Persist run.json."""
        run_path = self.run_dir(record.id, record.output_dir) / "run.json"
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(record.model_dump_json(indent=2))

    def read_run(self, run_id: str, output_dir: str = ".micro-eval/runs") -> RunRecord:
        """Read canonical run.json."""
        path = self.run_dir(run_id, output_dir) / "run.json"
        if not path.exists():
            raise RunStoreError(f"Run not found: {run_id}")
        return RunRecord.model_validate_json(path.read_text())

    def append_cell_result(self, record: RunRecord, result: CellResult) -> RunRecord:
        """Persist one cell result and update run.json."""
        cell_dir = self.run_dir(record.id, record.output_dir) / "cells" / safe_path_segment(result.cell_id)
        cell_dir.mkdir(parents=True, exist_ok=True)
        (cell_dir / "result.json").write_text(result.model_dump_json(indent=2))
        record.results = [item for item in record.results if item.cell_id != result.cell_id] + [result]
        self.write_run(record)
        return record

    def append_evaluation(
        self,
        *,
        run_id: str,
        cell_id: str,
        evaluation: EvaluationResult,
        evidence: EvidenceItem | None = None,
        output_dir: str = ".micro-eval/runs",
    ) -> RunRecord:
        """Append one evaluation and recompute the persisted run decision."""
        record = self.read_run(run_id, output_dir)
        cell_dir = self.run_dir(record.id, record.output_dir) / "cells" / safe_path_segment(cell_id)
        cell_dir.mkdir(parents=True, exist_ok=True)
        eval_path = cell_dir / "evaluation.json"
        evaluations: list[EvaluationResult] = []
        if eval_path.exists():
            import json

            evaluations = [EvaluationResult.model_validate(item) for item in json.loads(eval_path.read_text())]
        evaluations.append(evaluation)
        eval_path.write_text(
            "[\n"
            + ",\n".join(item.model_dump_json(indent=2) for item in evaluations)
            + "\n]"
        )

        if evidence is not None:
            record.evidence = [item for item in record.evidence if item.evidence_id != evidence.evidence_id] + [evidence]
        record.evaluations = [
            item for item in record.evaluations if item.evaluation_id != evaluation.evaluation_id
        ] + [evaluation]
        for result in record.results:
            if result.cell_id != cell_id:
                continue
            if evaluation.evaluation_id not in result.evaluation_refs:
                result.evaluation_refs.append(evaluation.evaluation_id)
            for evidence_id in evaluation.evidence_refs:
                if evidence_id not in result.evidence_refs:
                    result.evidence_refs.append(evidence_id)
            if evaluation.evaluator_type == "human":
                result.pass_fail = evaluation.pass_fail
                result.score = evaluation.score
        record.decision = build_decision(record)
        self.write_run(record)
        return record

    def finalize_run(self, record: RunRecord) -> RunRecord:
        """Mark a run complete or partial based on cell results."""
        record.completed_at = datetime.now(timezone.utc).isoformat()
        record.status = RunStatus.completed if len(record.results) == len(record.cells) else RunStatus.partial
        self.write_run(record)
        return record

    def list_runs(self, output_dir: str = ".micro-eval/runs") -> list[RunRecord | dict[str, Any]]:
        """List canonical runs, with legacy flat JSON fallback."""
        runs_dir = self.project_root / output_dir
        if not runs_dir.exists():
            return []
        runs: list[RunRecord | dict[str, Any]] = []
        for path in sorted(runs_dir.iterdir()):
            try:
                if path.is_dir() and (path / "run.json").exists():
                    runs.append(RunRecord.model_validate_json((path / "run.json").read_text()))
                elif path.is_file() and path.suffix == ".json":
                    import json

                    runs.append(json.loads(path.read_text()))
            except Exception:
                continue
        runs.sort(key=lambda item: _run_sort_key(item), reverse=True)
        return runs

    def latest_run_id(self, output_dir: str = ".micro-eval/runs") -> str | None:
        """Return newest run id if any."""
        runs = self.list_runs(output_dir)
        if not runs:
            return None
        first = runs[0]
        if isinstance(first, RunRecord):
            return first.id
        return str(first.get("id"))


def _run_sort_key(item: RunRecord | dict[str, Any]) -> str:
    if isinstance(item, RunRecord):
        return item.created_at
    return str(item.get("timestamp") or item.get("created_at") or item.get("id") or "")
