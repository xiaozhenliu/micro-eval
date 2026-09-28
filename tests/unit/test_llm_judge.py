"""LLM judge supplemental evaluation coverage."""

from __future__ import annotations

from micro_eval.engine.adapter import Redactor
from micro_eval.evaluation.llm_judge import JudgeOutcome, build_judge_prompt, evaluate_cell_with_judge
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, JudgeConfig
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.run import AdapterResult, CellStatus, RunCell
from micro_eval.models.task import RubricSpec, TaskSpec


class FakeJudgeClient:
    name = "fake-judge"

    def judge(self, *, prompt, cell, result, config):  # noqa: ANN001
        return JudgeOutcome(score=1.0, pass_fail="pass", rationale="looks good but secret-token", scores={"overall": 1.0})


def test_judge_prompt_includes_rubric_and_validation_context() -> None:
    cell = _cell(rubric=RubricSpec(text="Score correctness", dimensions=["correctness", "clarity"]))
    validation = EvaluationResult(
        evaluation_id="validator",
        cell_id=cell.cell_id,
        pass_fail="fail",
        score=0.0,
        evidence_refs=["evidence-1"],
        comment="missing expected text",
    )

    prompt = build_judge_prompt(
        cell=cell,
        adapter_result=AdapterResult(status=CellStatus.passed, stdout="agent output"),
        validation=validation,
        evidence=[EvidenceItem(evidence_id="evidence-1", kind="validation", summary="stdout missing expected text")],
        redactor=Redactor({}),
    )

    assert "Score correctness" in prompt
    assert "correctness" in prompt
    assert "pass_fail=fail" in prompt
    assert "stdout missing expected text" in prompt


def test_llm_judge_result_is_redacted_and_cites_rationale_evidence() -> None:
    cell = _cell(rubric="Judge task alignment")
    validation = EvaluationResult(
        evaluation_id="validator",
        cell_id=cell.cell_id,
        pass_fail="fail",
        score=0.0,
        evidence_refs=["evidence-1"],
        comment="failed deterministic validation",
    )

    result = evaluate_cell_with_judge(
        cell=cell,
        adapter_result=AdapterResult(status=CellStatus.passed, stdout="agent output"),
        validation=validation,
        validation_evidence=[EvidenceItem(evidence_id="evidence-1", kind="validation", summary="failed")],
        config=JudgeConfig(enabled=True, model="mock-model"),
        redactor=Redactor({"MICRO_EVAL_SECRET_TOKEN": "secret-token"}),
        evidence_prefix="cell::evidence",
        client=FakeJudgeClient(),
    )

    assert result is not None
    evaluation, evidence = result
    assert evaluation.evaluator_type == "llm_judge"
    assert evaluation.pass_fail == "pass"
    assert evaluation.rubric_hash is not None
    assert evidence.kind == "judge_rationale"
    assert "secret-token" not in evidence.summary
    assert "[REDACTED:MICRO_EVAL_SECRET_TOKEN]" in evidence.summary
    assert evidence.evidence_id in evaluation.evidence_refs


def test_build_judge_prompt_redacts_secrets_before_truncation() -> None:
    """Secrets in task input, stdout, stderr, expected_output are removed from the prompt."""
    secret_value = "sk-supersecrettoken1234"
    redactor = Redactor({"MICRO_EVAL_SECRET_API_KEY": secret_value})
    # Build a task whose fields all embed the secret.
    config = ConfigurationSpec(id="cfg", name="cfg", agent=AgentSpec(name="agent", command=["python", "-c", "print('ok')"]))
    task = TaskSpec(
        id="task-secret",
        name="Task",
        description=f"describe the key {secret_value}",
        input_payload=f"call API with key={secret_value}",
        expected_output=f"output contains {secret_value}",
        rubric="Score task alignment",
    )
    cell = RunCell(cell_id="cell-secret", task=task, configuration=config)
    adapter_result = AdapterResult(
        status=CellStatus.passed,
        stdout=f"agent says {secret_value}",
        stderr=f"error log {secret_value}",
    )
    validation = EvaluationResult(
        evaluation_id="validator",
        cell_id=cell.cell_id,
        pass_fail="pass",
        score=1.0,
        evidence_refs=["ev-1"],
        comment=f"validation comment {secret_value}",
    )
    evidence = [EvidenceItem(evidence_id="ev-1", kind="validation", summary=f"evidence {secret_value}")]

    prompt = build_judge_prompt(
        cell=cell,
        adapter_result=adapter_result,
        validation=validation,
        evidence=evidence,
        redactor=redactor,
    )

    assert secret_value not in prompt
    assert "[REDACTED:MICRO_EVAL_SECRET_API_KEY]" in prompt


def _cell(*, rubric: str | RubricSpec) -> RunCell:
    config = ConfigurationSpec(id="cfg", name="cfg", agent=AgentSpec(name="agent", command=["python", "-c", "print('ok')"]))
    return RunCell(
        cell_id="cell-judge",
        task=TaskSpec(id="task", name="Task", input_payload="input", rubric=rubric),
        configuration=config,
    )
