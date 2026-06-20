"""Conversational evaluation via DeepEval ConversationSimulator."""

from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path

from micro_eval.engine.adapter import Redactor
from micro_eval.engine.agent_bridge import BridgeError, SubprocessBridge
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.configuration import AgentSpec, JudgeConfig
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.ids import compact_timestamp, rubric_digest, sha256_text
from micro_eval.models.run import AdapterResult, CellStatus, RunCell
from micro_eval.models.task import RubricSpec

logger = logging.getLogger(__name__)

METRIC_REGISTRY: dict[str, str] = {
    "conversation_completeness": "ConversationCompletenessMetric",
    "turn_relevancy": "TurnRelevancyMetric",
    "knowledge_retention": "KnowledgeRetentionMetric",
    "role_adherence": "RoleAdherenceMetric",
    "goal_accuracy": "GoalAccuracyMetric",
}
DEFAULT_METRICS = ["conversation_completeness", "turn_relevancy"]


async def simulate_conversation(
    *,
    cell: RunCell,
    config: JudgeConfig,
    agent: AgentSpec,
    cwd: Path,
    env: dict[str, str],
    redactor: Redactor,
) -> tuple[object, AdapterResult, list[dict[str, str]]] | None:
    """Phase 1: Drive multi-turn conversation, return test_case + results.

    Does NOT score — returns the raw ConversationalTestCase for scoring later.
    This split enables Invariant #6: deterministic validation between simulation and scoring.
    """
    task = cell.task
    if not task.scenario:
        return None

    deepeval_top = importlib.import_module("deepeval")
    deepeval_test_case = importlib.import_module("deepeval.test_case")
    deepeval_dataset = importlib.import_module("deepeval.dataset")
    deepeval_simulator = importlib.import_module("deepeval.simulator")
    Turn = getattr(deepeval_test_case, "Turn")
    ConversationalGolden = getattr(deepeval_dataset, "ConversationalGolden")
    ConversationSimulator = getattr(deepeval_simulator, "ConversationSimulator")

    bridge = SubprocessBridge(
        agent=agent, cwd=cwd, env=env, turn_timeout_s=config.turn_timeout_s,
    )
    await bridge.start()

    conversation_log: list[dict[str, str]] = []
    main_loop = asyncio.get_running_loop()

    def model_callback(input: str) -> object:
        conversation_log.append({"role": "user", "content": input})
        try:
            future = asyncio.run_coroutine_threadsafe(bridge.send_turn(input), main_loop)
            response = future.result(timeout=config.turn_timeout_s)
        except BridgeError as exc:
            response = f"[bridge error: {exc}]"
        except Exception as exc:
            response = f"[bridge error: {exc}]"
        response = redactor.redact(response)
        conversation_log.append({"role": "assistant", "content": response})
        return Turn(role="assistant", content=response)

    golden = ConversationalGolden(
        scenario=task.scenario,
        expected_outcome=task.expected_outcome or "",
        user_description=task.user_description or "",
    )

    try:
        simulator_kwargs = {"model_callback": model_callback}
        if config.simulator_model:
            simulator_kwargs["simulator_model"] = config.simulator_model
        simulator = ConversationSimulator(**simulator_kwargs)

        def _run_simulate():
            return simulator.simulate(
                conversational_goldens=[golden],
                max_user_simulations=config.max_turns,
            )

        test_cases = await asyncio.get_running_loop().run_in_executor(None, _run_simulate)
    except Exception as exc:
        logger.warning("ConversationSimulator failed: %s", exc)
        return None
    finally:
        exit_code, stderr = await bridge.stop()

    if not test_cases:
        return None
    test_case = test_cases[0]

    last_output = ""
    for entry in reversed(conversation_log):
        if entry["role"] == "assistant":
            last_output = entry["content"]
            break

    adapter_result = AdapterResult(
        status=CellStatus.passed if exit_code is None or exit_code == 0 else CellStatus.error,
        exit_code=exit_code,
        stdout="",
        stderr=stderr or "",
        output=last_output,
        latency_s=0.0,
        trace_id=cell.cell_id,
    )

    return test_case, adapter_result, conversation_log


async def score_conversation(
    *,
    cell: RunCell,
    config: JudgeConfig,
    test_case: object,
    turn_count: int,
    redactor: Redactor,
    evidence_prefix: str,
) -> tuple[EvaluationResult, EvidenceItem] | None:
    """Phase 2: Score a completed conversation using DeepEval metrics.

    Called AFTER deterministic validation passes (Invariant #6).
    """
    deepeval_top = importlib.import_module("deepeval")
    deepeval_metrics = importlib.import_module("deepeval.metrics")
    deepeval_evaluate = getattr(deepeval_top, "evaluate")

    metric_names = config.conversational_metrics or DEFAULT_METRICS
    metrics = []
    for name in metric_names:
        cls_name = METRIC_REGISTRY.get(name)
        if cls_name:
            cls = getattr(deepeval_metrics, cls_name, None)
            if cls:
                metrics.append(cls(threshold=config.pass_threshold))

    rubric = _rubric_text(cell)
    if rubric and hasattr(deepeval_metrics, "ConversationalGEval"):
        metrics.append(
            deepeval_metrics.ConversationalGEval(
                name="rubric",
                criteria=rubric,
                threshold=config.pass_threshold,
            )
        )

    if not metrics:
        logger.warning("No valid conversational metrics configured")
        return None

    try:
        def _run_evaluate():
            return deepeval_evaluate(
                test_cases=[test_case], metrics=metrics
            )

        eval_result = await asyncio.get_running_loop().run_in_executor(None, _run_evaluate)
    except Exception as exc:
        logger.warning("DeepEval evaluate failed: %s", exc)
        return None

    scores: dict[str, float] = {}
    all_pass = True
    for tr in eval_result.test_results:
        if not tr.success:
            all_pass = False
        for md in (tr.metrics_data or []):
            metric_score = getattr(md, "score", None)
            metric_name = getattr(md, "name", getattr(md, "metric", "unknown"))
            if metric_score is not None:
                scores[str(metric_name)] = float(metric_score)

    avg_score = sum(scores.values()) / len(scores) if scores else None
    pass_fail = "pass" if all_pass else "fail"

    rationale_parts = [f"{k}={v:.2f}" for k, v in scores.items()]
    rationale = redactor.redact(f"conversational eval: {'; '.join(rationale_parts)}")[:500]

    evidence_id = f"{evidence_prefix}::conversational-judge"
    evidence = EvidenceItem(
        evidence_id=evidence_id,
        kind="conversational_judge",
        cell_id=cell.cell_id,
        status="passed" if pass_fail == "pass" else "failed",
        severity="info",
        summary=rationale,
        source_kind="evaluation_id",
        metadata={
            "provider": "deepeval_conversational",
            "turn_count": turn_count,
            "metrics": ",".join(scores.keys()),
        },
    )

    evaluation_id = f"{cell.cell_id}::conversational-judge::{sha256_text(str(scores))[:12]}"
    evaluation = EvaluationResult(
        evaluation_id=evaluation_id,
        cell_id=cell.cell_id,
        evaluator_type="conversational_judge",
        evaluator="deepeval_conversational",
        evaluator_meta={
            "turn_count": turn_count,
            "simulator_model": config.simulator_model or "default",
            "metrics": ",".join(scores.keys()),
        },
        rubric_hash=rubric_digest(cell.task.rubric),
        pass_fail=pass_fail,
        score=avg_score,
        scores=scores,
        comment=rationale,
        evidence_refs=[evidence_id],
        created_at=compact_timestamp(),
    )
    evidence.source_ref = evaluation_id

    return evaluation, evidence


def _rubric_text(cell: RunCell) -> str:
    rubric = cell.task.rubric
    if rubric is None:
        return ""
    if isinstance(rubric, str):
        return rubric
    if isinstance(rubric, RubricSpec):
        dimensions = "; ".join(str(item) for item in rubric.dimensions)
        return f"{rubric.text}\nDimensions: {dimensions}"
    return str(rubric)
