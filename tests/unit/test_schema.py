"""Tests for Pydantic schema models."""

from micro_eval.models.schema import (
    AgentConfig,
    EnvironmentSnapshot,
    InputMode,
    OutputMode,
    Run,
    RunResult,
    Task,
    TaskStatus,
)


def test_agent_config_defaults():
    agent = AgentConfig(name="test", command="echo hi")
    assert agent.input_mode == InputMode.stdin
    assert agent.output_mode == OutputMode.stdout
    assert agent.timeout_s == 300.0
    assert agent.env == {}


def test_agent_config_custom():
    agent = AgentConfig(
        name="custom",
        command="python run.py",
        input_mode=InputMode.file,
        output_mode=OutputMode.file,
        timeout_s=60.0,
        env={"API_KEY": "test"},
    )
    assert agent.input_mode == InputMode.file
    assert agent.output_mode == OutputMode.file
    assert agent.timeout_s == 60.0
    assert agent.env["API_KEY"] == "test"


def test_task_minimal():
    task = Task(id="t1", name="Test", input_payload="hello")
    assert task.description == ""
    assert task.expected_output is None
    assert task.rubric is None
    assert task.business_impact_tier == 3
    assert task.tags == []


def test_task_full():
    task = Task(
        id="t2",
        name="Full task",
        description="A complete task",
        input_payload="input data",
        expected_output="expected",
        rubric="Must match exactly",
        business_impact_tier=1,
        tags=["smoke"],
    )
    assert task.expected_output == "expected"
    assert task.business_impact_tier == 1


def test_run_result():
    result = RunResult(
        task_id="t1",
        agent_name="agent-a",
        status=TaskStatus.passed,
        score=0.95,
        output_summary="hello",
        latency_s=1.5,
    )
    assert result.status == TaskStatus.passed
    assert result.score == 0.95
    assert result.stdout_summary == ""
    assert result.stderr_summary == ""
    assert result.exit_code is None
    assert result.output_artifacts == []
    assert result.failure_mode is None


def test_run_result_error():
    result = RunResult(
        task_id="t1",
        agent_name="agent-a",
        status=TaskStatus.error,
        latency_s=0.1,
        failure_mode="exit_code_1",
    )
    assert result.status == TaskStatus.error
    assert result.failure_mode == "exit_code_1"


def test_environment_snapshot():
    env = EnvironmentSnapshot(
        git_commit="abc123",
        config_hash="def456",
        python_version="3.11.0",
        timestamp="2024-01-01T00:00:00Z",
    )
    assert env.git_commit == "abc123"


def test_run_model():
    run = Run(
        id="run-123",
        baseline_agent="baseline",
        candidate_agent="candidate",
        tasks=["t1", "t2"],
    )
    assert run.schema_version == "1.0"
    assert run.execution_order == "parallel"
    assert run.results == []


def test_run_serialization():
    run = Run(
        id="run-456",
        timestamp="2024-01-01T00:00:00Z",
        baseline_agent="b",
        candidate_agent="c",
        tasks=["t1"],
        results=[
            RunResult(
                task_id="t1",
                agent_name="b",
                status=TaskStatus.passed,
                score=1.0,
                output_summary="ok",
                stdout_summary="ok",
                stderr_summary="",
                stdout_ref=".micro-eval/artifacts/run-456/t1--b/stdout.txt",
                stderr_ref=".micro-eval/artifacts/run-456/t1--b/stderr.txt",
                exit_code=0,
                output_dir=".micro-eval/artifacts/run-456/t1--b",
                output_artifacts=[],
                latency_s=0.5,
            )
        ],
    )
    data = run.model_dump()
    assert data["schema_version"] == "1.0"
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "pass"
    assert data["results"][0]["stdout_ref"].endswith("stdout.txt")
    assert data["results"][0]["exit_code"] == 0
