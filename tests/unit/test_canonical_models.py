"""Acceptance tests for canonical Pydantic models."""

import pytest
from pydantic import ValidationError

from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, Guardrails, JudgeConfig
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.run import CellResult, CellStatus
from micro_eval.models.task import ExpectationSpec, TaskSpec


def test_guardrails_defaults_match_spec():
    # #9: spec defaults are concurrency 4 and a distinct, larger artifact cap.
    guardrails = Guardrails()
    assert guardrails.max_concurrency == 4
    assert guardrails.output_cap_bytes == 10 * 1024 * 1024
    assert guardrails.artifact_cap_bytes == 50 * 1024 * 1024
    assert guardrails.artifact_cap_bytes > guardrails.output_cap_bytes


def test_cell_result_persists_truncation_flags():
    # #9: truncation flags computed by the adapter must survive on CellResult.
    result = CellResult(
        cell_id="c1",
        run_id="r1",
        task_id="t1",
        configuration_id="cfg",
        configuration_name="cfg",
        repetition=1,
        status=CellStatus.passed,
        output_truncated=True,
        stdout_truncated=True,
    )
    assert result.output_truncated is True
    assert result.stdout_truncated is True
    assert result.stderr_truncated is False  # default


def test_agent_spec_requires_argv_list():
    with pytest.raises(ValidationError):
        AgentSpec(name="bad", command="cat")  # type: ignore[arg-type]

    agent = AgentSpec(name="ok", command=["cat"])
    assert agent.command == ["cat"]


def test_configuration_repetitions_and_digest_are_canonical():
    agent = AgentSpec(name="agent", command=["cat"])
    config = ConfigurationSpec(id="cfg", name="Config", agent=agent, repetitions=2)
    assert config.repetitions == 2
    assert len(config.digest) == 64


def test_task_and_configuration_ids_must_be_path_safe():
    agent = AgentSpec(name="agent", command=["cat"])
    with pytest.raises(ValidationError, match="path-safe"):
        ConfigurationSpec(id="../cfg", name="Config", agent=agent)
    with pytest.raises(ValidationError, match="path-safe"):
        TaskSpec(id="../task", name="Task", input_payload="hello")


def test_task_spec_supports_deterministic_expectations():
    task = TaskSpec(
        id="t1",
        name="Task",
        input_payload="hello",
        expectations=[ExpectationSpec(type="contains", value="hello")],
    )
    assert task.expectations[0].type == "contains"


def test_command_expectation_requires_argv_list():
    with pytest.raises(ValidationError):
        ExpectationSpec(type="command")


def test_pass_fail_evaluation_requires_evidence_refs():
    with pytest.raises(ValidationError):
        EvaluationResult(evaluation_id="e1", cell_id="c1", pass_fail="pass")


def test_task_spec_conversational_fields_default_none():
    """Conversational fields are optional — existing tasks must not break."""
    task = TaskSpec(id="t", name="T", input_payload="hello")
    assert task.scenario is None
    assert task.expected_outcome is None
    assert task.user_description is None


def test_task_spec_conversational_fields_roundtrip():
    """Conversational fields survive JSON serialization."""
    task = TaskSpec(
        id="conv", name="Conv", input_payload="ctx",
        scenario="test scenario",
        expected_outcome="agent succeeds",
        user_description="a tester",
    )
    data = task.model_dump(mode="json")
    restored = TaskSpec.model_validate(data)
    assert restored.scenario == "test scenario"
    assert restored.expected_outcome == "agent succeeds"
    assert restored.user_description == "a tester"


def test_judge_config_default_provider_unchanged():
    """Existing eval.yaml without provider field should default to 'deepeval'."""
    config = JudgeConfig(enabled=True)
    assert config.provider == "deepeval"


def test_judge_config_accepts_conversational_provider():
    config = JudgeConfig(enabled=True, provider="deepeval_conversational")
    assert config.provider == "deepeval_conversational"
    assert config.max_turns == 10
    assert config.turn_timeout_s == 60.0
    assert config.conversational_metrics == []


def test_judge_config_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        JudgeConfig(enabled=True, provider="unknown_provider")


def test_cell_result_conversational_fields_default():
    """Existing CellResult construction must not break."""
    result = CellResult(
        cell_id="c1", run_id="r1", task_id="t1",
        configuration_id="cfg", configuration_name="cfg",
        repetition=1, status=CellStatus.passed,
    )
    assert result.conversation_turns == 0
    assert result.conversation_ref is None


def test_cell_result_conversational_fields_roundtrip():
    result = CellResult(
        cell_id="c1", run_id="r1", task_id="t1",
        configuration_id="cfg", configuration_name="cfg",
        repetition=1, status=CellStatus.passed,
        conversation_turns=5,
        conversation_ref="c1::conversation::abc123",
    )
    data = result.model_dump(mode="json")
    restored = CellResult.model_validate(data)
    assert restored.conversation_turns == 5
    assert restored.conversation_ref == "c1::conversation::abc123"
