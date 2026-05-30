"""End-to-end test: config load -> run -> report."""

import asyncio
import json
from pathlib import Path

import pytest

from micro_eval.config.loader import load_config, load_tasks
from micro_eval.engine.runner import AgentRunner
from micro_eval.engine.scorer import Scorer
from micro_eval.models.schema import Run, TaskStatus

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_full_eval_flow(tmp_path):
    """Complete flow: load config, run eval, score, save."""
    # Load config and tasks
    config = load_config(FIXTURES / "eval.yaml")
    tasks = load_tasks(FIXTURES / "tasks")
    assert len(tasks) >= 1

    # Run evaluation
    runner = AgentRunner(work_dir=tmp_path)
    run = await runner.run_eval(
        baseline=config.baseline,
        candidate=config.candidate,
        tasks=tasks,
        parallel=config.parallel,
    )

    # Verify run structure
    assert run.id.startswith("run-")
    assert run.schema_version == "1.0"
    assert len(run.results) == 2  # 1 task x 2 agents

    # Score results
    scorer = Scorer()
    for result in run.results:
        task = next(t for t in tasks if t.id == result.task_id)
        result.score = scorer.score(result, task)
        result.status = scorer.judge_pass_fail(result, task)

    # Both should pass (cat echoes input)
    for result in run.results:
        assert result.status == TaskStatus.passed
        assert result.score == 1.0

    # Save to JSON
    output_file = tmp_path / "result.json"
    output_file.write_text(run.model_dump_json(indent=2))

    # Verify JSON is valid and re-parseable
    loaded = json.loads(output_file.read_text())
    reloaded_run = Run(**loaded)
    assert reloaded_run.id == run.id
    assert len(reloaded_run.results) == 2


@pytest.mark.asyncio
async def test_failing_agent_flow(tmp_path):
    """Test with an agent that fails."""
    from micro_eval.models.schema import AgentConfig, Task

    baseline = AgentConfig(name="good", command="cat")
    candidate = AgentConfig(name="bad", command="false")
    task = Task(
        id="t1",
        name="Fail test",
        input_payload="test",
        expected_output="test",
    )

    runner = AgentRunner(work_dir=tmp_path)
    run = await runner.run_eval(baseline, candidate, [task], parallel=True)

    scorer = Scorer()
    for result in run.results:
        result.score = scorer.score(result, task)

    # baseline passes, candidate fails
    baseline_result = next(
        r for r in run.results if r.agent_name == "good"
    )
    candidate_result = next(
        r for r in run.results if r.agent_name == "bad"
    )
    assert baseline_result.score == 1.0
    assert candidate_result.score == 0.0
