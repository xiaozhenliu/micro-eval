"""Canonical execution kernel over RunPlan."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from pathlib import Path

from micro_eval.engine.adapter import AgentAdapter, Redactor
from micro_eval.engine.cell_lifecycle import CellLifecycle, FinalizedCell
from micro_eval.engine.workspace import WorkspaceManager
from micro_eval.evaluation.llm_judge import resolve_judge_client
from micro_eval.evaluation.validator import validate_cell
from micro_eval.models.run import CellResult, CellStatus, RunCell, RunPlan, RunRecord
from micro_eval.store.artifact_store import ArtifactStore
from micro_eval.store.run_store import RunStore
from micro_eval.trace.process_provider import ProcessTraceProvider
from micro_eval.trace.provider import TraceProvider

logger = logging.getLogger(__name__)


class ExecutionKernel:
    """Execute RunPlan cells with bounded concurrency."""

    SUMMARY_LIMIT = 500

    def __init__(
        self,
        project_root: Path | str,
        on_cell_complete: Callable | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ):
        self.project_root = Path(project_root)
        self.run_store = RunStore(self.project_root)
        self._on_cell_complete = on_cell_complete
        self._cancel_requested = cancel_requested

    async def run(self, plan: RunPlan) -> RunRecord:
        """Execute all cells in a plan and persist canonical run artifacts."""
        record = self.run_store.init_run(plan)
        run_dir = self.run_store.run_dir(plan.run_id, plan.output_dir)
        artifact_store = ArtifactStore(run_dir, artifact_cap_bytes=plan.guardrails.artifact_cap_bytes)
        adapter = AgentAdapter(output_cap_bytes=plan.guardrails.output_cap_bytes)
        workspace_manager = WorkspaceManager(self.project_root, run_id=plan.run_id)
        trace_providers = self._trace_providers(plan)
        judge_client = resolve_judge_client(plan.judge)
        lifecycle = CellLifecycle(
            project_root=self.project_root.resolve(),
            record=record,
            plan=plan,
            adapter=adapter,
            artifact_store=artifact_store,
            workspace_manager=workspace_manager,
            trace_providers=trace_providers,
            judge_client=judge_client,
            validator=validate_cell,
        )
        # Determine dispatch order. Randomization (opt-in) avoids order-effect bias
        # in serial / >2-way comparisons; the order (and seed) are recorded so the
        # run stays reproducible. Default off keeps deterministic plan order.
        cells = list(plan.cells)
        if plan.guardrails.randomize_execution_order:
            seed = random.randrange(2**32)
            random.Random(seed).shuffle(cells)
            record.execution_seed = seed
        pending = iter(cells)

        async def dispatch_cells() -> None:
            nonlocal record
            while True:
                # Only active workers take the next cell. Checking before each
                # dispatch lets in-flight cells finish without starting queued ones.
                if self._cancel_requested and self._cancel_requested():
                    return
                try:
                    cell = next(pending)
                except StopIteration:
                    return
                record.execution_order.append(cell.cell_id)
                finalized = await self._run_cell(cell, lifecycle, record)
                record = self.run_store.commit_cell(record, finalized)
                if self._on_cell_complete:
                    self._on_cell_complete(len(record.results), len(cells), finalized.result)

        tasks = [
            asyncio.create_task(dispatch_cells())
            for _ in range(min(plan.guardrails.max_concurrency, len(cells)))
        ]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        record.artifacts = artifact_store.manifest.artifacts
        record.evidence = artifact_store.manifest.evidence
        record.traces = artifact_store.manifest.traces
        # Cross-run comparability: warn when a configuration id was reused with
        # changed content vs a prior run (#2). Surfaced via snapshot caveats
        # so build_decision folds it into the decision's comparability caveats.
        if record.same_start_snapshot is not None:
            record.same_start_snapshot.caveats.extend(
                self.run_store.configuration_drift_caveats(record)
            )
        return self.run_store.finalize_run(
            record,
            cancelled=bool(self._cancel_requested and self._cancel_requested()),
        )

    async def _run_cell(
        self,
        cell: RunCell,
        lifecycle: CellLifecycle,
        record: RunRecord,
    ) -> FinalizedCell:
        """Isolate one cell so an unexpected error cannot abort sibling cells."""
        try:
            # CellLifecycle delegates process execution to adapter.invoke().
            return await lifecycle.execute(cell)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - per-cell isolation boundary.
            logger.error("Unexpected %s in cell %s; isolating as error result", type(exc).__name__, cell.cell_id)
            return FinalizedCell(
                result=self._isolated_failure_result(cell, record, exc),
                evaluations=(),
            )

    def _isolated_failure_result(self, cell: RunCell, record: RunRecord, exc: Exception) -> CellResult:
        """Build an error CellResult for an unexpected per-cell failure."""
        # str(exc) may carry secrets (paths, args); redact before persisting/exposing.
        redactor = Redactor.from_env()
        redactor.values.update({
            key: value for key, value in cell.configuration.agent.env.items()
            if key.startswith(Redactor.SECRET_ENV_PREFIX) and value
        })
        return CellResult(
            cell_id=cell.cell_id,
            run_id=record.id,
            task_id=cell.task.id,
            configuration_id=cell.configuration.id,
            configuration_name=cell.configuration.name,
            repetition=cell.repetition,
            status=CellStatus.error,
            score=0.0,
            pass_fail="fail",
            stderr_summary=redactor.redact(str(exc))[: self.SUMMARY_LIMIT],
            failure_mode=f"kernel_error:{exc.__class__.__name__}",
            cell_snapshot=getattr(getattr(exc, "prepared_workspace", None), "snapshot", None),
        )

    def _trace_providers(self, plan: RunPlan) -> list[TraceProvider]:
        """Resolve optional trace providers with process fallback."""
        providers: list[TraceProvider] = []
        if plan.trace.enabled and plan.trace.provider == "langfuse":
            try:
                from micro_eval.trace.langfuse_provider import LangfuseProvider

                langfuse = LangfuseProvider.from_env()
                if langfuse is not None:
                    providers.append(langfuse)
            except Exception:
                pass
        providers.append(ProcessTraceProvider())
        return providers
