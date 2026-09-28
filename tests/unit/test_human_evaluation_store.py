"""Phase 1 human evaluation persistence coverage."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from micro_eval.config.planner import build_run_plan
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.evaluation.human import build_human_evaluation
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, ProjectConfigV2
from micro_eval.models.task import TaskSpec
from micro_eval.store.run_store import RunStore


def test_append_human_evaluation_updates_cell_file_and_decision(tmp_path: Path) -> None:
    task = TaskSpec(id="task", name="Task", input_payload="hello")
    config = ProjectConfigV2(
        project_name="human-eval-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(name="agent", command=[sys.executable, "-c", "print('hello')"]),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)
    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    cell_id = record.results[0].cell_id

    evaluation, evidence = build_human_evaluation(
        cell_id=cell_id,
        pass_fail="fail",
        score=0.0,
        comment="human found a missing behavior",
    )
    updated = RunStore(tmp_path).append_evaluation(
        run_id=record.id,
        cell_id=cell_id,
        evaluation=evaluation,
        evidence=evidence,
    )

    eval_path = tmp_path / ".micro-eval" / "runs" / record.id / "cells" / cell_id / "evaluation.json"
    assert eval_path.exists()
    assert evaluation.evaluation_id in eval_path.read_text()
    result = updated.results[0]
    assert result.pass_fail == "fail"
    assert result.score == 0.0
    assert evaluation.evaluation_id in result.evaluation_refs
    assert evidence.evidence_id in result.evidence_refs
    assert updated.decision is not None
    assert evaluation.evaluation_id in updated.decision.evaluation_refs
    assert updated.decision.aggregation["agent"].pass_rate == 0.0


def test_human_evaluation_redacts_micro_eval_secret_comments(monkeypatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_REVIEW", "secret-val")

    evaluation, evidence = build_human_evaluation(
        cell_id="cell",
        pass_fail="pass",
        score=1.0,
        comment="contains secret-val here",
    )

    assert "secret-val" not in evaluation.comment
    assert "secret-val" not in evidence.summary
    assert "[REDACTED:MICRO_EVAL_SECRET_REVIEW]" in evaluation.comment
