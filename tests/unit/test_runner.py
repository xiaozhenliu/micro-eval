"""Tests for the agent runner."""

import re
import sys

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
    assert (tmp_path / result.stderr_ref).read_text() == ""
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
async def test_run_single_python_placeholder_uses_current_interpreter(sample_task, tmp_path):
    agent = AgentConfig(
        name="python-placeholder",
        command="{python} -c 'import sys; print(sys.executable)'",
    )
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.passed
    assert sys.executable in result.stdout_summary


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
    output_refs = [ref for ref in result.output_artifacts if ref.endswith("output.txt")]
    assert output_refs
    assert (tmp_path / output_refs[0]).read_text() == "file result"


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
    answer_refs = [ref for ref in result.output_artifacts if ref.endswith("answer.txt")]
    assert answer_refs
    assert (tmp_path / answer_refs[0]).read_text() == "directory result"


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
async def test_run_single_redacts_short_micro_eval_secret_from_artifacts(sample_task, tmp_path, monkeypatch):
    monkeypatch.setenv("MICRO_EVAL_SECRET_SHORT", "xy")
    secret_task = Task(
        id="task-short-secret",
        name="Short secret",
        input_payload="xy",
        expected_output="xy",
    )
    agent = AgentConfig(name="secret-echo", command="cat")
    runner = AgentRunner(work_dir=tmp_path)

    result = await runner._run_single(agent, secret_task)

    assert result.status == TaskStatus.passed
    assert "xy" not in result.output_summary
    assert "[REDACTED]" in result.output_summary
    assert result.stdout_ref is not None
    assert "xy" not in (tmp_path / result.stdout_ref).read_text()


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
async def test_run_eval_same_agent_name_uses_distinct_artifact_paths(
    sample_task, tmp_path
):
    baseline_agent = AgentConfig(name="same-agent", command="cat")
    candidate_agent = AgentConfig(name="same-agent", command="cat")
    runner = AgentRunner(work_dir=tmp_path)

    run = await runner.run_eval(
        baseline_agent, candidate_agent, [sample_task], parallel=True
    )

    stdout_refs = [result.stdout_ref for result in run.results]
    stderr_refs = [result.stderr_ref for result in run.results]
    output_dirs = [result.output_dir for result in run.results]

    assert len(run.results) == 2
    assert len(set(stdout_refs)) == 2
    assert len(set(stderr_refs)) == 2
    assert len(set(output_dirs)) == 2
    assert all(ref is not None for ref in stdout_refs)
    assert all(ref is not None for ref in stderr_refs)
    assert all(path is not None for path in output_dirs)
    assert any("--baseline--" in str(path) for path in output_dirs)
    assert any("--candidate--" in str(path) for path in output_dirs)
    for ref in stdout_refs + stderr_refs:
        assert ref is not None
        assert (tmp_path / ref).exists()


@pytest.mark.asyncio
async def test_run_eval_generates_distinct_readable_run_ids(
    baseline, candidate, sample_task, tmp_path
):
    runner = AgentRunner(work_dir=tmp_path)

    first = await runner.run_eval(baseline, candidate, [sample_task])
    second = await runner.run_eval(baseline, candidate, [sample_task])

    pattern = r"^run-\d{8}T\d{6}Z-[0-9a-f]{8}$"
    assert first.id != second.id
    assert re.match(pattern, first.id)
    assert re.match(pattern, second.id)


@pytest.mark.asyncio
async def test_run_eval_sequential(baseline, candidate, sample_task, tmp_path):
    runner = AgentRunner(work_dir=tmp_path)
    run = await runner.run_eval(
        baseline, candidate, [sample_task], parallel=False
    )
    assert run.execution_order == "sequential"
    assert len(run.results) == 2
