"""Canonical run store for local JSON data."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from micro_eval.models.run import CellResult, RunPlan, RunRecord, RunStatus
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.decision import DecisionReport
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
            denominator_policy=plan.denominator_policy,
        )
        self.write_run(record)
        return record

    def write_run(self, record: RunRecord) -> None:
        """Persist run.json and the Phase 2 decision.json projection."""
        run_dir = self.run_dir(record.id, record.output_dir)
        run_path = run_dir / "run.json"
        run_path.parent.mkdir(parents=True, exist_ok=True)
        run_path.write_text(record.model_dump_json(indent=2))
        if record.decision is not None:
            self.write_decision(record)

    def write_decision(self, record: RunRecord) -> None:
        """Persist decision.json beside run.json when a decision exists."""
        if record.decision is None:
            return
        decision_path = self.run_dir(record.id, record.output_dir) / "decision.json"
        decision_path.write_text(record.decision.model_dump_json(indent=2))

    def read_run(self, run_id: str, output_dir: str = ".micro-eval/runs") -> RunRecord:
        """Read canonical run.json, preferring sibling decision.json when present."""
        run_dir = self.run_dir(run_id, output_dir)
        path = run_dir / "run.json"
        if not path.exists():
            raise RunStoreError(f"Run not found: {run_id}")
        record = RunRecord.model_validate_json(path.read_text())
        decision_path = run_dir / "decision.json"
        if decision_path.exists():
            record.decision = DecisionReport.model_validate_json(decision_path.read_text())
        return record

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
        self._index_to_sqlite(record)
        return record

    def _index_to_sqlite(self, record: RunRecord) -> None:
        """Best-effort index to SQLite for trend queries."""
        try:
            from micro_eval.store.sqlite_store import SqliteStore

            store = SqliteStore(self.project_root)
            try:
                store.index_run(record)
            finally:
                store.close()
        except Exception:
            pass

    def list_runs(self, output_dir: str = ".micro-eval/runs") -> list[RunRecord | dict[str, Any]]:
        """List canonical runs, with legacy flat JSON fallback."""
        runs_dir = self.project_root / output_dir
        if not runs_dir.exists():
            return []
        runs: list[RunRecord | dict[str, Any]] = []
        for path in sorted(runs_dir.iterdir()):
            try:
                if path.is_dir() and (path / "run.json").exists():
                    record = RunRecord.model_validate_json((path / "run.json").read_text())
                    decision_path = path / "decision.json"
                    if decision_path.exists():
                        record.decision = DecisionReport.model_validate_json(decision_path.read_text())
                    runs.append(record)
                # Legacy flat .json files at the runs root are ignored (GRO-194).
                # Only the canonical subdirectory layout (run-id/run.json) is
                # parsed to prevent loading arbitrary JSON files.
            except Exception:
                continue
        runs.sort(key=lambda item: _run_sort_key(item), reverse=True)
        return runs

    def configuration_drift_caveats(
        self, record: RunRecord, output_dir: str = ".micro-eval/runs"
    ) -> list[str]:
        """Caveats for configurations whose content changed under a reused id (#2).

        A configuration id is the identity used to compare runs. If its content
        (its recorded digest) differs from the most recent prior run that used
        the same id, results across those runs are not directly comparable —
        the same "column" no longer means the same thing. We surface this as a
        cross-run comparability caveat rather than silently comparing.
        """
        current = (
            record.same_start_snapshot.configuration_digests
            if record.same_start_snapshot
            else {}
        )
        if not current:
            return []
        # list_runs returns newest-first; the current (unwritten) run is excluded.
        priors = [
            run
            for run in self.list_runs(output_dir)
            if isinstance(run, RunRecord) and run.id != record.id and run.same_start_snapshot
        ]
        caveats: list[str] = []
        for config_id, digest in current.items():
            for prior in priors:
                prior_digests = prior.same_start_snapshot.configuration_digests
                if config_id not in prior_digests:
                    continue
                if prior_digests[config_id] != digest:
                    caveats.append(
                        f"configuration '{config_id}' content changed since run {prior.id} "
                        f"(digest {prior_digests[config_id][:8]}→{digest[:8]}); "
                        "results may not be comparable across runs"
                    )
                break  # only compare against the most recent prior run with this id
        return caveats

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
