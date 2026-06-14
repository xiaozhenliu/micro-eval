"""Acceptance tests for canonical Pydantic models."""

import pytest
from pydantic import ValidationError

from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, Guardrails
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
