"""Normal cell lifecycle shared by single and conversational invocations."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from micro_eval.engine.adapter import AdapterError, AgentAdapter, Redactor
from micro_eval.engine.workspace import (
    PreparedWorkspace,
    WorkspaceError,
    WorkspaceManager,
    evaluate_snapshot_gate,
)
from micro_eval.evaluation.conversational_judge import score_conversation, simulate_conversation
from micro_eval.evaluation.llm_judge import JudgeClient, evaluate_cell_with_judge
from micro_eval.evaluation.validator import validate_cell
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.environment import CellSnapshot, SnapshotGateResult
from micro_eval.models.run import AdapterResult, CellResult, CellStatus, RunCell, RunPlan, RunRecord
from micro_eval.store.artifact_store import ArtifactStore
from micro_eval.trace.provider import TraceProvider, collect_trace_with_fallback


@dataclass
class InvocationOutcome:
    """Facts returned by either invocation mode before common finalization."""

    adapter_result: AdapterResult
    redactor: Redactor
    conversation_test_case: object | None = None
    conversation_log: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class FinalizedCell:
    """Stable result and evaluations after normal cleanup has completed."""

    result: CellResult
    evaluations: tuple[EvaluationResult, ...]


class CellLifecycle:
    """Deep normal-path module for one cell's prepare-to-commit facts.

    The scheduler sees only ``execute``. Single-turn and conversational
    invocation differ only in how they produce InvocationOutcome; all
    terminal observation, evidence, validation, judgment, and cleanup rules
    live in the shared finalization path below.
    """

    SUMMARY_LIMIT = 500

    def __init__(
        self,
        *,
        project_root: Path,
        record: RunRecord,
        plan: RunPlan,
        adapter: AgentAdapter,
        artifact_store: ArtifactStore,
        workspace_manager: WorkspaceManager,
        trace_providers: list[TraceProvider],
        judge_client: JudgeClient | None,
        validator: Callable = validate_cell,
    ) -> None:
        self.project_root = project_root
        self.record = record
        self.plan = plan
        self.adapter = adapter
        self.artifact_store = artifact_store
        self.workspace_manager = workspace_manager
        self.trace_providers = trace_providers
        self.judge_client = judge_client
        self.validator = validator

    async def execute(self, cell: RunCell) -> FinalizedCell:
        """Run one cell through the normal lifecycle in its required order."""
        prepared: PreparedWorkspace | None = None
        workspace_caveats: list[str] = []
        snapshot_gate: SnapshotGateResult | None = None
        try:
            prepared = self.workspace_manager.prepare(
                cell_id=cell.cell_id,
                workspace=cell.task.workspace,
                caveats=workspace_caveats,
            )
            snapshot_gate = self._snapshot_gate(cell, prepared, workspace_caveats)
            if self._uses_conversation(cell):
                outcome = await self._invoke_conversation(cell, prepared)
            else:
                adapter_result, redactor = await self.adapter.invoke(
                    agent=cell.configuration.agent,
                    input_payload=cell.task.input_payload,
                    cwd=prepared.path,
                    output_dir=self.artifact_store.cell_dir(cell.cell_id),
                    trace_id=cell.cell_id,
                )
                outcome = InvocationOutcome(adapter_result=adapter_result, redactor=redactor)
        except (WorkspaceError, AdapterError) as exc:
            redactor = Redactor.from_env()
            outcome = InvocationOutcome(
                adapter_result=AdapterResult(
                    status=CellStatus.error,
                    stderr=redactor.redact(str(exc)),
                    failure_mode=exc.__class__.__name__,
                    trace_id=cell.cell_id,
                ),
                redactor=redactor,
            )
            if prepared is None:
                prepared = PreparedWorkspace(
                    path=self.project_root,
                    snapshot=CellSnapshot(
                        workspace_path=str(self.project_root),
                        timestamp=self.record.created_at,
                    ),
                    cleanup_kind="none",
                )

        if prepared is None:
            raise RuntimeError("cell lifecycle did not produce a prepared workspace")
        if snapshot_gate is None:
            snapshot_gate = self._snapshot_gate(cell, prepared, workspace_caveats)
        return await self._finalize(cell, prepared, outcome, snapshot_gate)

    def _snapshot_gate(
        self,
        cell: RunCell,
        prepared: PreparedWorkspace,
        workspace_caveats: list[str],
    ) -> SnapshotGateResult:
        """Evaluate the prepared start before invoking the agent."""
        snapshot_gate = evaluate_snapshot_gate(
            self.record.same_start_snapshot,
            prepared.snapshot,
            task_id=cell.task.id,
        )
        if workspace_caveats:
            snapshot_gate.caveats.extend(dict.fromkeys(workspace_caveats))
            if snapshot_gate.status == "pass":
                snapshot_gate.status = "warn"
        return snapshot_gate

    def _uses_conversation(self, cell: RunCell) -> bool:
        return bool(
            self.plan.judge.enabled
            and self.plan.judge.provider == "deepeval_conversational"
            and cell.task.scenario is not None
        )

    async def _invoke_conversation(
        self, cell: RunCell, prepared: PreparedWorkspace
    ) -> InvocationOutcome:
        """Run the conversational adapter only; scoring stays in finalization."""
        cell_dir = self.artifact_store.cell_dir(cell.cell_id)
        env, redactor = self.adapter.build_env(
            cell.configuration.agent,
            cell_dir,
            cell_dir / "output.txt",
            cell.cell_id,
        )
        started = time.monotonic()
        simulation = await simulate_conversation(
            cell=cell,
            config=self.plan.judge,
            agent=cell.configuration.agent,
            cwd=prepared.path,
            env=env,
            redactor=redactor,
        )
        if simulation is None:
            return InvocationOutcome(
                adapter_result=AdapterResult(
                    status=CellStatus.error,
                    stderr="conversation simulation failed",
                    failure_mode="conversation_simulation_failed",
                    trace_id=cell.cell_id,
                    latency_s=time.monotonic() - started,
                ),
                redactor=redactor,
            )
        test_case, adapter_result, conversation_log = simulation
        adapter_result.latency_s = time.monotonic() - started
        adapter_result.stderr = redactor.redact(adapter_result.stderr)
        return InvocationOutcome(
            adapter_result=adapter_result,
            redactor=redactor,
            conversation_test_case=test_case,
            conversation_log=conversation_log,
        )

    async def _finalize(
        self,
        cell: RunCell,
        prepared: PreparedWorkspace,
        outcome: InvocationOutcome,
        snapshot_gate: SnapshotGateResult,
    ) -> FinalizedCell:
        """Finalize a cell and clean it even if finalization is interrupted."""
        try:
            finalized = await self._finalize_live(
                cell, prepared, outcome, snapshot_gate
            )
        except BaseException:
            if prepared.cleanup_kind != "none":
                self.workspace_manager.cleanup_workspace(prepared)
            raise
        if prepared.cleanup_kind != "none":
            finalized.result.cell_snapshot = self.workspace_manager.cleanup_workspace(prepared)
        return finalized

    async def _finalize_live(
        self,
        cell: RunCell,
        prepared: PreparedWorkspace,
        outcome: InvocationOutcome,
        snapshot_gate: SnapshotGateResult,
    ) -> FinalizedCell:
        """Observe, persist, validate, judge, clean, and return stable facts."""
        cell_dir = self.artifact_store.cell_dir(cell.cell_id)
        adapter_result = outcome.adapter_result
        redactor = outcome.redactor

        # This is intentionally the first post-invocation workspace operation.
        # Validators may mutate the workspace, so their side effects must not
        # contaminate the validation-before-state diff.
        observation = self.workspace_manager.observe_final(
            prepared,
            byte_limit=self.plan.guardrails.artifact_cap_bytes,
        )
        all_caveats = list(observation.warnings)
        if observation.diff_truncated:
            all_caveats.append("diff_truncated")
        if all_caveats:
            snapshot_gate.caveats.extend(dict.fromkeys(all_caveats))
            if snapshot_gate.status == "pass":
                snapshot_gate.status = "warn"

        workspace_artifacts = list(
            self.artifact_store.persist_workspace_observation(
                cell.cell_id, observation, redactor
            )
        )
        artifacts = list(workspace_artifacts)
        if outcome.conversation_log:
            conversation_artifact = self.artifact_store.write_text(
                cell.cell_id,
                "conversation",
                "conversation.json",
                json.dumps(outcome.conversation_log, indent=2, ensure_ascii=False),
            )
            artifacts.append(conversation_artifact)
        else:
            conversation_artifact = None

        artifacts.extend(
            [
                self.artifact_store.write_text(
                    cell.cell_id, "stdout", "stdout.txt", adapter_result.stdout
                ),
                self.artifact_store.write_text(
                    cell.cell_id, "stderr", "stderr.txt", adapter_result.stderr
                ),
            ]
        )
        if adapter_result.output:
            artifacts.append(
                self.artifact_store.write_text(
                    cell.cell_id, "output", "output.txt", adapter_result.output
                )
            )
        if adapter_result.output_artifacts:
            artifacts.extend(
                self.artifact_store.index_existing_outputs(
                    cell.cell_id,
                    exclude_names={"input.txt", "stdout.txt", "stderr.txt", "output.txt"},
                    include_paths=adapter_result.output_artifacts,
                )
            )

        evidence_prefix = f"{cell.cell_id}::evidence"
        process_evidence = EvidenceItem(
            evidence_id=f"{evidence_prefix}::process",
            kind="process",
            source_kind="artifact_ref",
            source_ref=next(
                (artifact.artifact_id for artifact in artifacts if artifact.kind == "stdout"),
                artifacts[0].artifact_id if artifacts else None,
            ),
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
        self.artifact_store.add_evidence(process_evidence)

        workspace_evidence = EvidenceItem(
            evidence_id=f"{evidence_prefix}::workspace",
            kind="workspace_observation",
            source_kind="artifact_ref",
            source_ref=workspace_artifacts[0].artifact_id if workspace_artifacts else None,
            cell_id=cell.cell_id,
            status="passed" if not observation.warnings else "warning",
            severity="info" if not observation.warnings else "warning",
            summary=redactor.redact(
                "workspace observation "
                f"type={observation.workspace_type.value}; "
                f"diff={'present' if observation.diff_text else 'none'}; "
                f"warnings={','.join(observation.warnings) or 'none'}"
            )[: self.SUMMARY_LIMIT],
            artifact_refs=[artifact.artifact_id for artifact in workspace_artifacts],
            metadata={
                "workspace_type": observation.workspace_type.value,
                "diff_truncated": observation.diff_truncated,
                "warning_count": len(observation.warnings),
            },
        )
        self.artifact_store.add_evidence(workspace_evidence)

        trace_refs: list[str] = []
        trace = collect_trace_with_fallback(
            self.trace_providers,
            cell=cell,
            result=adapter_result,
            redactor=redactor,
        )
        if trace is not None:
            self.artifact_store.add_trace(trace)
            trace_refs.append(f"{trace.provider}:{trace.trace_id}")

        snapshot_evidence = EvidenceItem(
            evidence_id=f"{evidence_prefix}::snapshot-gate",
            kind="snapshot",
            cell_id=cell.cell_id,
            status="passed" if snapshot_gate.status == "pass" else "failed",
            severity="info" if snapshot_gate.status == "pass" else "critical",
            summary=redactor.redact(
                "snapshot gate "
                f"{snapshot_gate.status}; "
                f"mismatches={','.join(snapshot_gate.mismatch_fields) or 'none'}"
            )[: self.SUMMARY_LIMIT],
            metadata={
                "gate_status": snapshot_gate.status,
                "mismatch_count": len(snapshot_gate.mismatch_fields),
                "caveat_count": len(snapshot_gate.caveats),
            },
        )
        self.artifact_store.add_evidence(snapshot_evidence)

        # Validation must run against the same live workspace that was
        # observed above. Cleanup is deliberately below all evaluation work.
        validation, validation_evidence = await self.validator(
            cell=cell,
            adapter_result=adapter_result,
            cell_dir=cell_dir,
            evidence_prefix=evidence_prefix,
            redactor=redactor,
            workspace_dir=prepared.path,
        )
        for evidence in validation_evidence:
            self.artifact_store.add_evidence(evidence)

        evaluations = [validation]
        judge_evidence: EvidenceItem | None = None
        if outcome.conversation_test_case is not None:
            if validation.pass_fail != "fail" and adapter_result.status != CellStatus.error:
                scored = await score_conversation(
                    cell=cell,
                    config=self.plan.judge,
                    test_case=outcome.conversation_test_case,
                    turn_count=len(outcome.conversation_log) // 2,
                    redactor=redactor,
                    evidence_prefix=evidence_prefix,
                )
                if scored is not None:
                    judge_evaluation, judge_evidence = scored
                    evaluations.append(judge_evaluation)
        else:
            judged = evaluate_cell_with_judge(
                cell=cell,
                adapter_result=adapter_result,
                validation=validation,
                validation_evidence=validation_evidence,
                config=self.plan.judge,
                redactor=redactor,
                evidence_prefix=evidence_prefix,
                client=self.judge_client,
            )
            if judged is not None:
                judge_evaluation, judge_evidence = judged
                evaluations.append(judge_evaluation)
        if judge_evidence is not None:
            self.artifact_store.add_evidence(judge_evidence)

        evidence_items = [process_evidence, workspace_evidence, snapshot_evidence]
        evidence_items.extend(validation_evidence)
        if judge_evidence is not None:
            evidence_items.append(judge_evidence)

        final_evaluation = evaluations[-1]
        if outcome.conversation_test_case is not None:
            if adapter_result.status == CellStatus.error:
                cell_status = CellStatus.error
                cell_pass_fail = None
                cell_score = None
            else:
                cell_status = (
                    CellStatus.failed
                    if final_evaluation.pass_fail == "fail"
                    else adapter_result.status
                )
                cell_pass_fail = final_evaluation.pass_fail
                cell_score = final_evaluation.score
        else:
            cell_status = adapter_result.status
            if cell_status == CellStatus.passed and validation.pass_fail == "fail":
                cell_status = CellStatus.failed
            cell_pass_fail = validation.pass_fail
            cell_score = validation.score

        result = CellResult(
            cell_id=cell.cell_id,
            run_id=self.record.id,
            task_id=cell.task.id,
            configuration_id=cell.configuration.id,
            configuration_name=cell.configuration.name,
            repetition=cell.repetition,
            status=cell_status,
            score=cell_score,
            pass_fail=cell_pass_fail,
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
            evidence_refs=[item.evidence_id for item in evidence_items],
            evaluation_refs=[item.evaluation_id for item in evaluations],
            trace_refs=trace_refs,
            cell_snapshot=prepared.snapshot,
            snapshot_gate_result=snapshot_gate,
            conversation_turns=len(outcome.conversation_log) // 2,
            conversation_ref=conversation_artifact.artifact_id if conversation_artifact else None,
        )
        return FinalizedCell(result=result, evaluations=tuple(evaluations))
