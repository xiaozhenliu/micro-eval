"""Canonical execution kernel over RunPlan."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from pathlib import Path

from micro_eval.decision.summary import build_decision
from micro_eval.engine.adapter import AdapterError, AgentAdapter, Redactor
from micro_eval.engine.workspace import PreparedWorkspace, WorkspaceError, WorkspaceManager, evaluate_snapshot_gate
from micro_eval.evaluation.llm_judge import JudgeClient, evaluate_cell_with_judge, resolve_judge_client
from micro_eval.evaluation.validator import validate_cell
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.ids import safe_path_segment
from micro_eval.models.run import AdapterResult, CellResult, CellStatus, RunCell, RunPlan, RunRecord
from micro_eval.store.artifact_store import ArtifactStore
from micro_eval.store.run_store import RunStore
from micro_eval.trace.process_provider import ProcessTraceProvider
from micro_eval.trace.provider import TraceProvider, collect_trace_with_fallback

logger = logging.getLogger(__name__)


class ExecutionKernel:
    """Execute RunPlan cells with bounded concurrency."""

    SUMMARY_LIMIT = 500

    def __init__(self, project_root: Path | str, on_cell_complete: Callable | None = None):
        self.project_root = Path(project_root)
        self.run_store = RunStore(self.project_root)
        self._on_cell_complete = on_cell_complete

    async def run(self, plan: RunPlan) -> RunRecord:
        """Execute all cells in a plan and persist canonical run artifacts."""
        record = self.run_store.init_run(plan)
        run_dir = self.run_store.run_dir(plan.run_id, plan.output_dir)
        artifact_store = ArtifactStore(run_dir, artifact_cap_bytes=plan.guardrails.artifact_cap_bytes)
        adapter = AgentAdapter(output_cap_bytes=plan.guardrails.output_cap_bytes)
        workspace_manager = WorkspaceManager(self.project_root, run_id=plan.run_id)
        trace_providers = self._trace_providers(plan)
        judge_client = resolve_judge_client(plan.judge)
        semaphore = asyncio.Semaphore(plan.guardrails.max_concurrency)

        # Determine dispatch order. Randomization (opt-in) avoids order-effect bias
        # in serial / >2-way comparisons; the order (and seed) are recorded so the
        # run stays reproducible. Default off keeps deterministic plan order.
        cells = list(plan.cells)
        if plan.guardrails.randomize_execution_order:
            seed = random.randrange(2**32)
            random.Random(seed).shuffle(cells)
            record.execution_seed = seed
        record.execution_order = [cell.cell_id for cell in cells]

        async def run_cell(cell):
            async with semaphore:
                return await self._run_cell(cell, adapter, artifact_store, workspace_manager, record, trace_providers, judge_client, plan)

        tasks = [asyncio.create_task(run_cell(cell)) for cell in cells]
        for completed in asyncio.as_completed(tasks):
            result = await completed
            record = self.run_store.append_cell_result(record, result)
            if self._on_cell_complete:
                completed_count = len(record.results)
                total_count = len(cells)
                self._on_cell_complete(completed_count, total_count, result)
        record.artifacts = artifact_store.manifest.artifacts
        record.evidence = artifact_store.manifest.evidence
        record.traces = artifact_store.manifest.traces
        record.evaluations = []
        for result in record.results:
            eval_path = run_dir / "cells" / safe_path_segment(result.cell_id) / "evaluation.json"
            if eval_path.exists():
                import json

                record.evaluations.extend(
                    EvaluationResult.model_validate(item) for item in json.loads(eval_path.read_text())
                )
        # Cross-run comparability: warn when a configuration id was reused with
        # changed content vs a prior run (#2). Surfaced via the snapshot caveats
        # so build_decision folds it into the decision's comparability caveats.
        if record.same_start_snapshot is not None:
            record.same_start_snapshot.caveats.extend(
                self.run_store.configuration_drift_caveats(record)
            )
        record.decision = build_decision(record)
        record = self.run_store.finalize_run(record)
        return record

    async def _run_cell(
        self,
        cell: RunCell,
        adapter: AgentAdapter,
        artifact_store: ArtifactStore,
        workspace_manager: WorkspaceManager,
        record: RunRecord,
        trace_providers: list[TraceProvider],
        judge_client: JudgeClient | None,
        plan: RunPlan,
    ) -> CellResult:
        """Isolate one cell so an unexpected error cannot abort sibling cells."""
        try:
            return await self._execute_cell(
                cell, adapter, artifact_store, workspace_manager, record, trace_providers, judge_client, plan
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - per-cell isolation boundary; the run must still finalize.
            # Keep the full traceback observable for debugging while the run continues.
            logger.exception("Unexpected error in cell %s; isolating as error result", cell.cell_id)
            return self._isolated_failure_result(cell, record, exc)

    def _isolated_failure_result(self, cell: RunCell, record: RunRecord, exc: Exception) -> CellResult:
        """Build an error CellResult for an unexpected per-cell failure."""
        # str(exc) may carry secrets (paths, args); redact before persisting/exposing.
        redactor = Redactor.from_env()
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
        )

    async def _execute_cell(
        self,
        cell: RunCell,
        adapter: AgentAdapter,
        artifact_store: ArtifactStore,
        workspace_manager: WorkspaceManager,
        record: RunRecord,
        trace_providers: list[TraceProvider],
        judge_client: JudgeClient | None,
        plan: RunPlan,
    ) -> CellResult:
        cell_dir = artifact_store.cell_dir(cell.cell_id)
        prepared: PreparedWorkspace | None = None
        redactor = Redactor({})
        workspace_caveats: list[str] = []
        try:
            prepared = workspace_manager.prepare(
                cell_id=cell.cell_id,
                workspace=cell.task.workspace,
                caveats=workspace_caveats,
            )
            # Branch: conversational evaluation
            if (plan.judge.enabled
                    and plan.judge.provider == "deepeval_conversational"
                    and cell.task.scenario is not None):
                return await self._execute_cell_conversational(
                    cell, artifact_store, prepared, record, trace_providers, plan, cell_dir, workspace_caveats,
                )
            adapter_result, redactor = await adapter.invoke(
                agent=cell.configuration.agent,
                input_payload=cell.task.input_payload,
                cwd=prepared.path,
                output_dir=cell_dir,
                trace_id=cell.cell_id,
            )
        except (WorkspaceError, AdapterError) as exc:
            redactor = Redactor.from_env()
            adapter_result = AdapterResult(
                status=CellStatus.error,
                stderr=redactor.redact(str(exc)),
                failure_mode=exc.__class__.__name__,
                trace_id=cell.cell_id,
            )
            if prepared is None:
                from micro_eval.models.environment import CellSnapshot

                prepared = PreparedWorkspace(
                    path=self.project_root,
                    snapshot=CellSnapshot(
                        workspace_path=str(self.project_root),
                        timestamp=record.created_at,
                    ),
                    cleanup_kind="none",
                )
        finally:
            if prepared is not None and prepared.cleanup_kind != "none":
                workspace_manager.cleanup_workspace(prepared)

        assert prepared is not None
        snapshot_gate = evaluate_snapshot_gate(record.same_start_snapshot, prepared.snapshot, task_id=cell.task.id)
        if workspace_caveats:
            snapshot_gate.caveats.extend(workspace_caveats)
            if snapshot_gate.status == "pass":
                snapshot_gate.status = "warn"
        artifacts = [
            artifact_store.write_text(cell.cell_id, "stdout", "stdout.txt", adapter_result.stdout),
            artifact_store.write_text(cell.cell_id, "stderr", "stderr.txt", adapter_result.stderr),
        ]
        if adapter_result.output:
            artifacts.append(
                artifact_store.write_text(cell.cell_id, "output", "output.txt", adapter_result.output)
            )
        if adapter_result.output_artifacts:
            artifacts.extend(
                artifact_store.index_existing_outputs(
                    cell.cell_id,
                    exclude_names={"input.txt", "stdout.txt", "stderr.txt", "output.txt"},
                )
            )

        evidence_prefix = f"{cell.cell_id}::evidence"
        process_evidence = EvidenceItem(
            evidence_id=f"{evidence_prefix}::process",
            kind="process",
            source_kind="artifact_ref",
            source_ref=artifacts[0].artifact_id if artifacts else None,
            cell_id=cell.cell_id,
            status="passed" if adapter_result.status == CellStatus.passed else "error",
            severity="info" if adapter_result.status == CellStatus.passed else "warning",
            summary=f"status={adapter_result.status.value} exit_code={adapter_result.exit_code}",
            artifact_refs=[artifact.artifact_id for artifact in artifacts],
            metadata={
                "exit_code": adapter_result.exit_code,
                "latency_s": adapter_result.latency_s,
                "timed_out": adapter_result.timed_out,
                "trace_id": adapter_result.trace_id,
            },
        )
        artifact_store.add_evidence(process_evidence)
        trace = collect_trace_with_fallback(
            trace_providers,
            cell=cell,
            result=adapter_result,
            redactor=redactor,
        )
        trace_refs: list[str] = []
        if trace is not None:
            artifact_store.add_trace(trace)
            trace_refs.append(f"{trace.provider}:{trace.trace_id}")
        snapshot_evidence = EvidenceItem(
            evidence_id=f"{evidence_prefix}::snapshot-gate",
            kind="snapshot",
            cell_id=cell.cell_id,
            status="passed" if snapshot_gate.status == "pass" else "failed",
            severity="info" if snapshot_gate.status == "pass" else "critical",
            summary=redactor.redact(
                "snapshot gate "
                f"{snapshot_gate.status}; mismatches={','.join(snapshot_gate.mismatch_fields) or 'none'}"
            )[:500],
            metadata={"gate_status": snapshot_gate.status, "mismatch_count": len(snapshot_gate.mismatch_fields)},
        )
        artifact_store.add_evidence(snapshot_evidence)
        evaluation, validation_evidence = await validate_cell(
            cell=cell,
            adapter_result=adapter_result,
            cell_dir=cell_dir,
            evidence_prefix=evidence_prefix,
            redactor=redactor,
            workspace_dir=prepared.path,
        )
        for evidence in validation_evidence:
            artifact_store.add_evidence(evidence)
        evaluations = [evaluation]
        judge_result = evaluate_cell_with_judge(
            cell=cell,
            adapter_result=adapter_result,
            validation=evaluation,
            validation_evidence=validation_evidence,
            config=plan.judge,
            redactor=redactor,
            evidence_prefix=evidence_prefix,
            client=judge_client,
        )
        judge_evidence: EvidenceItem | None = None
        if judge_result is not None:
            judge_evaluation, judge_evidence = judge_result
            artifact_store.add_evidence(judge_evidence)
            evaluations.append(judge_evaluation)

        import json

        (cell_dir / "evaluation.json").write_text(
            json.dumps([item.model_dump(mode="json") for item in evaluations], indent=2)
        )
        evidence_refs = [process_evidence.evidence_id, snapshot_evidence.evidence_id] + [
            item.evidence_id for item in validation_evidence
        ]
        if judge_evidence is not None:
            evidence_refs.append(judge_evidence.evidence_id)
        status = adapter_result.status
        if status == CellStatus.passed and evaluation.pass_fail == "fail":
            status = CellStatus.failed
        return CellResult(
            cell_id=cell.cell_id,
            run_id=record.id,
            task_id=cell.task.id,
            configuration_id=cell.configuration.id,
            configuration_name=cell.configuration.name,
            repetition=cell.repetition,
            status=status,
            score=evaluation.score,
            pass_fail=evaluation.pass_fail,
            output_summary=adapter_result.output[: self.SUMMARY_LIMIT],
            stdout_summary=adapter_result.stdout[: self.SUMMARY_LIMIT],
            stderr_summary=adapter_result.stderr[: self.SUMMARY_LIMIT],
            exit_code=adapter_result.exit_code,
            latency_s=adapter_result.latency_s,
            failure_mode=adapter_result.failure_mode,
            stdout_truncated=adapter_result.stdout_truncated,
            stderr_truncated=adapter_result.stderr_truncated,
            output_truncated=adapter_result.output_truncated,
            artifact_refs=[artifact.artifact_id for artifact in artifacts],
            evidence_refs=evidence_refs,
            evaluation_refs=[item.evaluation_id for item in evaluations],
            trace_refs=trace_refs,
            cell_snapshot=prepared.snapshot if prepared else None,
            snapshot_gate_result=snapshot_gate,
        )


    async def _execute_cell_conversational(
        self,
        cell: RunCell,
        artifact_store: ArtifactStore,
        prepared: PreparedWorkspace,
        record: RunRecord,
        trace_providers: list[TraceProvider],
        plan: RunPlan,
        cell_dir: Path,
        workspace_caveats: list[str],
    ) -> CellResult:
        """Execute a cell using conversational evaluation (DeepEval ConversationSimulator)."""
        import json as json_mod
        import time

        from micro_eval.evaluation.conversational_judge import simulate_conversation, score_conversation

        agent = cell.configuration.agent
        adapter = AgentAdapter(output_cap_bytes=plan.guardrails.output_cap_bytes)
        env_base, redactor = adapter.build_env(
            agent, cell_dir, cell_dir / "output.txt", cell.cell_id,
        )

        start = time.monotonic()
        sim_result = await simulate_conversation(
            cell=cell,
            config=plan.judge,
            agent=agent,
            cwd=prepared.path,
            env=env_base,
            redactor=redactor,
        )
        latency = time.monotonic() - start

        if sim_result is None:
            return self._isolated_failure_result(cell, record, RuntimeError("conversation simulation returned None"))

        test_case, adapter_result, conversation_log = sim_result
        adapter_result.latency_s = latency
        adapter_result.stderr = redactor.redact(adapter_result.stderr)

        evidence_prefix = f"{cell.cell_id}::evidence"

        artifacts = [
            artifact_store.write_text(cell.cell_id, "stdout", "stdout.txt", adapter_result.stdout),
            artifact_store.write_text(cell.cell_id, "stderr", "stderr.txt", adapter_result.stderr),
        ]
        conv_artifact = artifact_store.write_text(
            cell.cell_id, "conversation", "conversation.json",
            json_mod.dumps(conversation_log, indent=2, ensure_ascii=False),
        )
        artifacts.append(conv_artifact)

        process_evidence = EvidenceItem(
            evidence_id=f"{evidence_prefix}::process",
            kind="process",
            source_kind="artifact_ref",
            source_ref=artifacts[0].artifact_id if artifacts else None,
            cell_id=cell.cell_id,
            status="passed" if adapter_result.status == CellStatus.passed else "error",
            severity="info" if adapter_result.status == CellStatus.passed else "warning",
            summary=f"status={adapter_result.status.value} exit_code={adapter_result.exit_code}",
            artifact_refs=[a.artifact_id for a in artifacts],
            metadata={
                "exit_code": adapter_result.exit_code,
                "latency_s": adapter_result.latency_s,
                "timed_out": adapter_result.timed_out,
                "trace_id": adapter_result.trace_id,
            },
        )
        artifact_store.add_evidence(process_evidence)

        trace = collect_trace_with_fallback(trace_providers, cell=cell, result=adapter_result, redactor=redactor)
        trace_refs: list[str] = []
        if trace is not None:
            artifact_store.add_trace(trace)
            trace_refs.append(f"{trace.provider}:{trace.trace_id}")

        snapshot_gate = evaluate_snapshot_gate(record.same_start_snapshot, prepared.snapshot, task_id=cell.task.id)
        if workspace_caveats:
            snapshot_gate.caveats.extend(workspace_caveats)
            if snapshot_gate.status == "pass":
                snapshot_gate.status = "warn"
        snapshot_evidence = EvidenceItem(
            evidence_id=f"{evidence_prefix}::snapshot-gate",
            kind="snapshot",
            cell_id=cell.cell_id,
            status="passed" if snapshot_gate.status == "pass" else "failed",
            severity="info" if snapshot_gate.status == "pass" else "critical",
            summary=redactor.redact(
                "snapshot gate "
                f"{snapshot_gate.status}; mismatches={','.join(snapshot_gate.mismatch_fields) or 'none'}"
            )[:500],
            metadata={"gate_status": snapshot_gate.status, "mismatch_count": len(snapshot_gate.mismatch_fields)},
        )
        artifact_store.add_evidence(snapshot_evidence)

        validation_eval, validation_evidence = await validate_cell(
            cell=cell,
            adapter_result=adapter_result,
            cell_dir=cell_dir,
            evidence_prefix=evidence_prefix,
            redactor=redactor,
            workspace_dir=prepared.path,
        )
        for ev in validation_evidence:
            artifact_store.add_evidence(ev)

        conv_evaluation = None
        conv_evidence = None
        if validation_eval.pass_fail != "fail" and adapter_result.status != CellStatus.error:
            score_result = await score_conversation(
                cell=cell,
                config=plan.judge,
                test_case=test_case,
                turn_count=len(conversation_log) // 2,
                redactor=redactor,
                evidence_prefix=evidence_prefix,
            )
            if score_result is not None:
                conv_evaluation, conv_evidence = score_result

        all_evidence = [process_evidence, snapshot_evidence] + validation_evidence[:]
        if conv_evidence is not None:
            all_evidence.append(conv_evidence)
            artifact_store.add_evidence(conv_evidence)

        evaluations = [validation_eval]
        if conv_evaluation is not None:
            evaluations.append(conv_evaluation)
        (cell_dir / "evaluation.json").write_text(
            json_mod.dumps([item.model_dump(mode="json") for item in evaluations], indent=2)
        )

        final_eval = conv_evaluation if conv_evaluation is not None else validation_eval

        # Bridge-error cells must not produce strong conclusions (Decision Safety).
        if adapter_result.status == CellStatus.error:
            cell_pass_fail = None
            cell_score = None
            cell_status = CellStatus.error
        else:
            cell_pass_fail = final_eval.pass_fail
            cell_score = final_eval.score
            cell_status = CellStatus.failed if final_eval.pass_fail == "fail" else adapter_result.status

        return CellResult(
            cell_id=cell.cell_id,
            run_id=record.id,
            task_id=cell.task.id,
            configuration_id=cell.configuration.id,
            configuration_name=cell.configuration.name,
            repetition=cell.repetition,
            status=cell_status,
            score=cell_score,
            pass_fail=cell_pass_fail,
            output_summary=adapter_result.output[:self.SUMMARY_LIMIT],
            stdout_summary=adapter_result.stdout[:self.SUMMARY_LIMIT],
            stderr_summary=adapter_result.stderr[:self.SUMMARY_LIMIT],
            exit_code=adapter_result.exit_code,
            latency_s=adapter_result.latency_s,
            artifact_refs=[a.artifact_id for a in artifacts],
            evidence_refs=[ev.evidence_id for ev in all_evidence],
            evaluation_refs=[e.evaluation_id for e in evaluations],
            trace_refs=trace_refs,
            cell_snapshot=prepared.snapshot,
            snapshot_gate_result=snapshot_gate,
            conversation_turns=len(conversation_log) // 2,
            conversation_ref=conv_artifact.artifact_id,
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
