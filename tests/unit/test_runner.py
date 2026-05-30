"""Tests for the agent runner."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

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
    assert result.latency_s > 0


@pytest.mark.asyncio
async def test_run_single_error(sample_task, tmp_path):
    agent = AgentConfig(name="bad", command="false")
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.error
    assert result.failure_mode is not None


@pytest.mark.asyncio
async def test_run_single_timeout(sample_task, tmp_path):
    agent = AgentConfig(name="slow", command="sleep 60", timeout_s=0.1)
    runner = AgentRunner(work_dir=tmp_path)
    result = await runner._run_single(agent, sample_task)
    assert result.status == TaskStatus.timeout
    assert result.failure_mode == "timeout"


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
