"""Tests for the agent runner."""

import pytest

from micro_eval.engine.runner import AgentRunner
from micro_eval.models.schema import (
    AgentConfig,
    InputMode,
    OutputMode,
    Task,
    TaskStatus,
)


@pytest.fixture
def baseline():
    return AgentConfig(name="baseline", command="cat")


@pytest.fixture
def candidate():
    return AgentConfig(name="candidate", command="cat")


@pytest.fixture
def sample_task():
    return Task(
        id="task-001",
        name="Echo test",
        input_payload="Hello, world!",
        expected_output="Hello, world!",
    )


@pytest.mark.asyncio
async def test_run_single_success(baseline, sample_task, tmp_path):
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(baseline, sample_task)
    assert result.task_id == "task-001"
    assert result.agent_name == "baseline"
    assert result.status == TaskStatus.passed
    assert "Hello, world!" in result.output_summary
    assert "Hello, world!" in result.stdout_summary
    assert result.stderr_summary == ""
    assert result.exit_code == 0
    assert result.stdout_ref is not None
    assert result.stderr_ref is not None
    assert result.output_dir is not None
    assert (tmp_path / result.stdout_ref).read_text() == "Hello, world!"
    assert result.latency_s > 0


@pytest.mark.asyncio
async def test_run_single_error(sample_task, tmp_path):
    agent = AgentConfig(
        name="bad",
        command="python -c 'import sys; print(\"boom\", file=sys.stderr); sys.exit(7)'",
    )
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.error
    assert result.exit_code == 7
    assert result.failure_mode == "exit_code_7"
    assert "boom" in result.stderr_summary
    assert result.stderr_ref is not None
    assert "boom" in (tmp_path / result.stderr_ref).read_text()


@pytest.mark.asyncio
async def test_run_single_timeout(sample_task, tmp_path):
    agent = AgentConfig(name="slow", command="sleep 60", timeout_s=0.1)
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.timeout
    assert result.failure_mode == "timeout"
    assert result.exit_code is not None
    assert result.output_dir is not None


@pytest.mark.asyncio
async def test_run_single_file_input(sample_task, tmp_path):
    agent = AgentConfig(
        name="file-reader",
        command="cat {input_file}",
        input_mode=InputMode.file,
    )
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.passed
    assert "Hello, world!" in result.output_summary


@pytest.mark.asyncio
async def test_run_single_file_output_records_artifact(sample_task, tmp_path):
    agent = AgentConfig(
        name="file-writer",
        command="python -c 'import os, pathlib; pathlib.Path(os.environ[\"MICRO_EVAL_OUTPUT_FILE\"]).write_text(\"file result\")'",
        output_mode=OutputMode.file,
    )
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.passed
    assert result.output_summary == "file result"
    assert result.output_artifacts
    assert any(ref.endswith("output.txt") for ref in result.output_artifacts)


@pytest.mark.asyncio
async def test_run_single_directory_output_records_artifact(sample_task, tmp_path):
    agent = AgentConfig(
        name="dir-writer",
        command="python -c 'import os, pathlib; pathlib.Path(os.environ[\"MICRO_EVAL_OUTPUT_DIR\"], \"answer.txt\").write_text(\"directory result\")'",
        output_mode=OutputMode.directory,
    )
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.passed
    assert result.output_artifacts
    assert any(ref.endswith("answer.txt") for ref in result.output_artifacts)


@pytest.mark.asyncio
async def test_run_single_redacts_agent_env_from_artifacts(sample_task, tmp_path):
    agent = AgentConfig(
        name="secret-writer",
        command="python -c 'import os; print(os.environ[\"SECRET_TOKEN\"])'",
        env={"SECRET_TOKEN": "secret-value-123"},
    )
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.passed
    assert "secret-value-123" not in result.output_summary
    assert "[REDACTED]" in result.output_summary
    assert result.stdout_ref is not None
    assert "secret-value-123" not in (tmp_path / result.stdout_ref).read_text()


@pytest.mark.asyncio
async def test_run_eval_parallel(baseline, candidate, sample_task, tmp_path):
    runner = AgentRunner(work_dir=tmp_path)
    run = await runner.run_eval(baseline, candidate, [sample_task], parallel=True)
    assert run.schema_version == "1.0"
    assert run.baseline_agent == "baseline"
    assert run.candidate_agent == "candidate"
    assert len(run.results) == 2
    assert run.execution_order == "parallel"


@pytest.mark.asyncio
async def test_run_eval_sequential(baseline, candidate, sample_task, tmp_path):
    runner = AgentRunner(work_dir=tmp_path)
    run = await runner.run_eval(
        baseline, candidate, [sample_task], parallel=False
    )
    assert run.execution_order == "sequential"
    assert len(run.results) == 2
