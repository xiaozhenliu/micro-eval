"""Validator observations and commands stay in the agent execution context."""

from __future__ import annotations

from pathlib import Path

import pytest

from micro_eval.engine.adapter import Redactor
from micro_eval.engine.providers.base import CommandResult, ExecutionRequest
from micro_eval.evaluation.validator import validate_cell
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec
from micro_eval.models.run import AdapterResult, CellStatus, RunCell
from micro_eval.models.task import ExpectationSpec, TaskSpec


class ContextSpy:
    def __init__(self, workspace: Path, *, remote: bool = True, output: Path | None = None):
        self.workspace_path = workspace
        self.output_path = output
        self.is_remote = remote
        self.python_executable = "/provider/bin/python"
        self.requests: list[ExecutionRequest] = []
        self.checked_paths: list[Path] = []
        self.command_result = CommandResult(exit_code=0, stdout="provider output")
        self.error: Exception | None = None

    async def execute(self, request: ExecutionRequest) -> CommandResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.command_result

    async def path_exists(self, path: Path) -> bool:
        self.checked_paths.append(path)
        if self.error is not None:
            raise self.error
        return True


async def _validate(
    tmp_path: Path,
    context: ContextSpy,
    expectations: list[ExpectationSpec],
    *,
    result: AdapterResult | None = None,
    redactor: Redactor | None = None,
    execution_available: bool = True,
):
    cell = RunCell(
        cell_id="provider-validator",
        task=TaskSpec(id="task", name="Task", input_payload="input", expectations=expectations),
        configuration=ConfigurationSpec(id="config", name="Config", agent=AgentSpec(name="agent", command=["agent"])),
    )
    return await validate_cell(
        cell=cell,
        adapter_result=result or AdapterResult(status=CellStatus.passed, exit_code=0),
        cell_dir=tmp_path,
        workspace_dir=tmp_path / "unused-host-workspace",
        execution_context=context,
        execution_available=execution_available,
        evidence_prefix="provider-evidence",
        redactor=redactor,
    )


async def test_workspace_file_exists_uses_provider_without_host_resolution(tmp_path: Path, monkeypatch) -> None:
    context = ContextSpy(Path("/provider/workspace"))
    original_resolve = Path.resolve

    def no_remote_resolve(path: Path, *args, **kwargs):
        assert not str(path).startswith("/provider/"), "remote path was resolved on the host"
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", no_remote_resolve)
    evaluation, _ = await _validate(tmp_path, context, [ExpectationSpec(type="file_exists", value="nested/../result.txt")])

    assert evaluation.pass_fail == "pass"
    assert context.checked_paths == [Path("/provider/workspace/result.txt")]


async def test_output_file_exists_checks_provider_output(tmp_path: Path) -> None:
    (tmp_path / "artifact.txt").write_text("collected")
    context = ContextSpy(Path("/provider/workspace"), output=Path("/provider/output"))
    evaluation, _ = await _validate(tmp_path, context, [ExpectationSpec(type="file_exists", value="{output_dir}/artifact.txt")])

    assert evaluation.pass_fail == "pass"
    assert context.checked_paths == [Path("/provider/output/artifact.txt")]


async def test_collected_output_file_rejects_host_symlink_escape(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (tmp_path / "outside.txt").write_text("outside")
    (output / "artifact.txt").symlink_to(tmp_path / "outside.txt")
    evaluation, _ = await _validate(output, None, [ExpectationSpec(type="file_exists", value="{output_dir}/artifact.txt")])

    assert evaluation.pass_fail == "fail"


@pytest.mark.parametrize("path", ["../outside", "nested/../../outside", "/outside", "/provider/workspace-other/file"])
@pytest.mark.parametrize("kind", ["file_exists", "command"])
async def test_remote_path_escape_never_reaches_provider(tmp_path: Path, path: str, kind: str) -> None:
    context = ContextSpy(Path("/provider/workspace"))
    expectation = (
        ExpectationSpec(type=kind, value=path)
        if kind == "file_exists"
        else ExpectationSpec(type=kind, command=["side-effect"], cwd=path)
    )
    evaluation, _ = await _validate(tmp_path, context, [expectation])

    assert evaluation.pass_fail == "fail"
    assert "escapes workspace directory" in evaluation.comment
    assert context.checked_paths == []
    assert context.requests == []


@pytest.mark.parametrize("kind", ["file_exists", "command"])
async def test_local_symlink_escape_never_reaches_provider(tmp_path: Path, kind: str) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    context = ContextSpy(workspace, remote=False)
    expectation = (
        ExpectationSpec(type=kind, value="link")
        if kind == "file_exists"
        else ExpectationSpec(type=kind, command=["side-effect"], cwd="link")
    )
    evaluation, _ = await _validate(tmp_path, context, [expectation])

    assert evaluation.pass_fail == "fail"
    assert context.checked_paths == []
    assert context.requests == []


async def test_remote_command_maps_python_output_and_cwd_without_host_environment(tmp_path: Path, monkeypatch) -> None:
    context = ContextSpy(Path("/provider/workspace"), output=Path("/provider/output"))
    for key in ("HOME", "PATH", "TMPDIR", "MICRO_EVAL_SECRET_KEY"):
        monkeypatch.setenv(key, "host-only")
    evaluation, _ = await _validate(
        tmp_path,
        context,
        [ExpectationSpec(type="command", command=["{python}", "{output_dir}/check.py"], cwd="checks/../checks", timeout_s=7)],
    )

    assert evaluation.pass_fail == "pass"
    assert len(context.requests) == 1
    request = context.requests[0]
    assert request.argv == ["/provider/bin/python", "/provider/output/check.py"]
    assert request.cwd == Path("/provider/workspace/checks")
    assert request.timeout_s == 7
    assert request.env == {}


async def test_local_context_commands_still_use_provider(tmp_path: Path) -> None:
    context = ContextSpy(tmp_path, remote=False)
    evaluation, _ = await _validate(tmp_path, context, [ExpectationSpec(type="command", command=["provider-only-binary"])])

    assert evaluation.pass_fail == "pass"
    assert context.requests[0].argv == ["provider-only-binary"]
    assert context.requests[0].cwd == tmp_path


async def test_command_output_cwd_uses_remote_output_scope(tmp_path: Path) -> None:
    context = ContextSpy(Path("/provider/workspace"), output=Path("/provider/output"))
    evaluation, _ = await _validate(
        tmp_path, context, [ExpectationSpec(type="command", command=["check"], cwd="{output_dir}/checks")]
    )

    assert evaluation.pass_fail == "pass"
    assert context.requests[0].cwd == Path("/provider/output/checks")


async def test_command_output_cwd_rejects_remote_output_escape(tmp_path: Path) -> None:
    context = ContextSpy(Path("/provider/workspace"), output=Path("/provider/output"))
    evaluation, _ = await _validate(
        tmp_path, context, [ExpectationSpec(type="command", command=["side-effect"], cwd="{output_dir}/../workspace")]
    )

    assert evaluation.pass_fail == "fail"
    assert context.requests == []


@pytest.mark.parametrize("use_cwd", [True, False])
async def test_command_requires_prepared_provider_output_when_referenced(tmp_path: Path, use_cwd: bool) -> None:
    context = ContextSpy(Path("/provider/workspace"))
    expectation = ExpectationSpec(
        type="command",
        command=["check"] if use_cwd else ["check", "{output_dir}/artifact"],
        cwd="{output_dir}" if use_cwd else None,
    )
    evaluation, _ = await _validate(tmp_path, context, [expectation])

    assert evaluation.pass_fail == "fail"
    assert "output directory is unavailable" in evaluation.comment
    assert context.requests == []


async def test_timed_out_agent_skips_commands_but_keeps_pure_expectations(tmp_path: Path) -> None:
    context = ContextSpy(Path("/provider/workspace"))
    evaluation, evidence = await _validate(
        tmp_path,
        context,
        [
            ExpectationSpec(type="command", command=["side-effect"]),
            ExpectationSpec(type="exit_code", value=0),
            ExpectationSpec(type="contains", value="partial", stream="stdout"),
        ],
        result=AdapterResult(status=CellStatus.failed, exit_code=0, stdout="partial", timed_out=True),
    )

    assert evaluation.pass_fail == "fail"
    assert "skipped because agent execution timed out" in evidence[0].summary
    assert [item.status for item in evidence] == ["failed", "passed", "passed"]
    assert context.requests == []


@pytest.mark.parametrize("kind", ["file_exists", "command"])
async def test_provider_errors_are_failed_redacted_evidence(tmp_path: Path, kind: str) -> None:
    secret = "provider-sensitive-credential"
    context = ContextSpy(Path("/provider/workspace"))
    context.error = RuntimeError(f"provider refused {secret}")
    evaluation, evidence = await _validate(
        tmp_path,
        context,
        [ExpectationSpec(type=kind, command=["check"], value="result.txt")],
        redactor=Redactor({"PROVIDER_TOKEN": secret}),
    )

    assert evaluation.pass_fail == "fail"
    assert secret not in evaluation.comment
    assert all(secret not in item.summary for item in evidence)
    assert "[REDACTED:PROVIDER_TOKEN]" in evaluation.comment


async def test_provider_timeout_is_a_failed_command(tmp_path: Path) -> None:
    context = ContextSpy(Path("/provider/workspace"))
    context.command_result = CommandResult(exit_code=0, timed_out=True)
    evaluation, _ = await _validate(tmp_path, context, [ExpectationSpec(type="command", command=["check"])])

    assert evaluation.pass_fail == "fail"
    assert "timed out" in evaluation.comment


async def test_unavailable_execution_skips_provider_checks_but_keeps_pure_checks(tmp_path: Path) -> None:
    context = ContextSpy(Path("/provider/workspace"))
    (tmp_path / "artifact.txt").write_text("collected")
    evaluation, evidence = await _validate(
        tmp_path,
        context,
        [
            ExpectationSpec(type="command", command=["side-effect"]),
            ExpectationSpec(type="file_exists", value="result.txt"),
            ExpectationSpec(type="file_exists", value="{output_dir}/artifact.txt"),
            ExpectationSpec(type="exit_code", value=0),
            ExpectationSpec(type="contains", value="", stream="stdout"),
        ],
        execution_available=False,
    )

    assert evaluation.pass_fail == "fail"
    assert all("validation unavailable" in item.summary for item in evidence[:3])
    assert [item.status for item in evidence] == ["failed", "failed", "failed", "passed", "passed"]
    assert context.requests == []
    assert context.checked_paths == []


async def test_unavailable_execution_without_context_cannot_run_host_command(tmp_path: Path) -> None:
    cell = RunCell(
        cell_id="unavailable-validator",
        task=TaskSpec(
            id="task",
            name="Task",
            input_payload="input",
            expectations=[ExpectationSpec(
                type="command",
                command=["{python}", "-c", "from pathlib import Path; Path('side-effect').write_text('ran')"],
            )],
        ),
        configuration=ConfigurationSpec(id="config", name="Config", agent=AgentSpec(name="agent", command=["agent"])),
    )
    evaluation, _ = await validate_cell(
        cell=cell,
        adapter_result=AdapterResult(status=CellStatus.error),
        cell_dir=tmp_path,
        workspace_dir=tmp_path,
        evidence_prefix="unavailable-evidence",
        execution_available=False,
    )

    assert evaluation.pass_fail == "fail"
    assert "validation unavailable" in evaluation.comment
    assert not (tmp_path / "side-effect").exists()
