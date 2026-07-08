"""Conversational judge unit tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from micro_eval.engine.adapter import Redactor
from micro_eval.evaluation.conversational_judge import (
    _rubric_text,
    simulate_conversation,
    score_conversation,
)
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, JudgeConfig
from micro_eval.models.run import RunCell
from micro_eval.models.task import RubricSpec, TaskSpec


def _conversational_cell(*, scenario="User asks a question", expected_outcome="Agent answers",
                          user_description="A student", rubric=None) -> RunCell:
    config = ConfigurationSpec(
        id="cfg", name="cfg",
        agent=AgentSpec(name="echo", command=[sys.executable, "-c",
            "import json,sys\n"
            "for line in sys.stdin:\n"
            "    d=json.loads(line)\n"
            "    print(json.dumps({'content':'ok: '+d['content']}),flush=True)\n"
        ]),
    )
    task = TaskSpec(
        id="conv-task",
        name="Conversation Task",
        input_payload="initial context",
        scenario=scenario,
        expected_outcome=expected_outcome,
        user_description=user_description,
        rubric=rubric,
    )
    return RunCell(cell_id="cell-conv", task=task, configuration=config)


def _single_turn_cell() -> RunCell:
    config = ConfigurationSpec(
        id="cfg", name="cfg",
        agent=AgentSpec(name="x", command=["true"]),
    )
    task = TaskSpec(id="t", name="T", input_payload="input")
    return RunCell(cell_id="c", task=task, configuration=config)


def test_conversational_cell_has_scenario() -> None:
    cell = _conversational_cell()
    assert cell.task.scenario is not None
    assert cell.task.expected_outcome is not None


def test_non_conversational_cell_has_no_scenario() -> None:
    cell = _single_turn_cell()
    assert cell.task.scenario is None


@pytest.mark.asyncio
async def test_evaluate_returns_none_without_scenario(tmp_path: Path) -> None:
    """Tasks without scenario field should return None immediately."""
    cell = _single_turn_cell()
    config = JudgeConfig(enabled=True, provider="deepeval_conversational")
    result = await simulate_conversation(
        cell=cell,
        config=config,
        agent=cell.configuration.agent,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        redactor=Redactor({}),
    )
    assert result is None


def test_rubric_text_from_string() -> None:
    cell = _conversational_cell(rubric="Evaluate helpfulness")
    assert _rubric_text(cell) == "Evaluate helpfulness"


def test_rubric_text_from_rubric_spec() -> None:
    rubric = RubricSpec(text="Score quality", dimensions=["accuracy", "clarity"])
    cell = _conversational_cell(rubric=rubric)
    text = _rubric_text(cell)
    assert "Score quality" in text
    assert "accuracy" in text
    assert "clarity" in text


def test_rubric_text_from_none() -> None:
    cell = _conversational_cell(rubric=None)
    assert _rubric_text(cell) == ""


@pytest.mark.asyncio
async def test_evaluate_cell_conversational_full_flow(tmp_path: Path) -> None:
    """Full flow with mocked DeepEval — verifies output structure."""
    cell = _conversational_cell()
    config = JudgeConfig(
        enabled=True, provider="deepeval_conversational",
        pass_threshold=0.5, max_turns=3, turn_timeout_s=5.0,
    )

    mock_turn = MagicMock()
    mock_turn_cls = MagicMock(return_value=mock_turn)

    mock_golden_cls = MagicMock()
    mock_golden = MagicMock()
    mock_golden_cls.return_value = mock_golden

    mock_test_case = MagicMock()
    mock_test_case.turns = [
        MagicMock(role="user", content="hi"),
        MagicMock(role="assistant", content="hello"),
    ]
    mock_simulator_cls = MagicMock()
    mock_simulator_instance = MagicMock()
    mock_simulator_instance.simulate.return_value = [mock_test_case]
    mock_simulator_cls.return_value = mock_simulator_instance

    mock_metric_data = MagicMock()
    mock_metric_data.score = 0.85
    mock_metric_data.name = "conversation_completeness"
    mock_test_result = MagicMock()
    mock_test_result.success = True
    mock_test_result.metrics_data = [mock_metric_data]
    mock_eval_result = MagicMock()
    mock_eval_result.test_results = [mock_test_result]

    mock_metric_cls = MagicMock()

    with patch.dict("sys.modules", {
        "deepeval.test_case": MagicMock(Turn=mock_turn_cls),
        "deepeval.dataset": MagicMock(ConversationalGolden=mock_golden_cls),
        "deepeval.simulator": MagicMock(ConversationSimulator=mock_simulator_cls),
        "deepeval.metrics": MagicMock(
            ConversationCompletenessMetric=mock_metric_cls,
            TurnRelevancyMetric=mock_metric_cls,
        ),
        "deepeval": MagicMock(evaluate=MagicMock(return_value=mock_eval_result)),
    }):
        sim_result = await simulate_conversation(
            cell=cell,
            config=config,
            agent=cell.configuration.agent,
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            redactor=Redactor({}),
        )

    assert sim_result is not None
    test_case_obj, adapter_result, conversation_log = sim_result
    assert isinstance(conversation_log, list)
    assert test_case_obj is not None

    with patch.dict("sys.modules", {
        "deepeval": MagicMock(evaluate=MagicMock(return_value=mock_eval_result)),
        "deepeval.metrics": MagicMock(
            ConversationCompletenessMetric=mock_metric_cls,
            TurnRelevancyMetric=mock_metric_cls,
        ),
    }):
        score_result = await score_conversation(
            cell=cell,
            config=config,
            test_case=test_case_obj,
            turn_count=len(conversation_log) // 2,
            redactor=Redactor({}),
            evidence_prefix="test::evidence",
        )

    assert score_result is not None
    evaluation, evidence = score_result

    assert evaluation.evaluator_type == "conversational_judge"
    assert evaluation.evaluator == "deepeval_conversational"
    assert evaluation.cell_id == "cell-conv"
    assert evaluation.score == 0.85
    assert evaluation.pass_fail == "pass"
    assert "conversation_completeness" in evaluation.scores

    assert evidence.kind == "conversational_judge"
    assert evidence.cell_id == "cell-conv"
    assert evidence.status == "passed"
    assert evidence.metadata["provider"] == "deepeval_conversational"


@pytest.mark.asyncio
async def test_evaluate_cell_conversational_simulator_failure(tmp_path: Path) -> None:
    """ConversationSimulator raising an exception should return None."""
    cell = _conversational_cell()
    config = JudgeConfig(enabled=True, provider="deepeval_conversational", turn_timeout_s=2.0)

    mock_simulator_cls = MagicMock()
    mock_simulator_instance = MagicMock()
    mock_simulator_instance.simulate.side_effect = RuntimeError("simulator broke")
    mock_simulator_cls.return_value = mock_simulator_instance

    with patch.dict("sys.modules", {
        "deepeval.test_case": MagicMock(Turn=MagicMock()),
        "deepeval.dataset": MagicMock(ConversationalGolden=MagicMock()),
        "deepeval.simulator": MagicMock(ConversationSimulator=mock_simulator_cls),
        "deepeval.metrics": MagicMock(),
        "deepeval": MagicMock(),
    }):
        result = await simulate_conversation(
            cell=cell,
            config=config,
            agent=cell.configuration.agent,
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            redactor=Redactor({}),
        )

    assert result is None
