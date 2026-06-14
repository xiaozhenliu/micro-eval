"""Acceptance tests for deterministic validation expectation branches."""

from __future__ import annotations

import sys
from pathlib import Path

from micro_eval.engine.adapter import Redactor
from micro_eval.evaluation.validator import validate_cell
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec
from micro_eval.models.run import AdapterResult, CellStatus, RunCell
from micro_eval.models.task import ExpectationSpec, TaskSpec


def _cell(expectations: list[ExpectationSpec]) -> RunCell:
    config = ConfigurationSpec(id="cfg", name="cfg", agent=AgentSpec(name="agent", command=["python", "-c", "print('ok')"]))
    task = TaskSpec(id="task", name="Task", input_payload="input", expectations=expectations)
    return RunCell(cell_id="cell-validator", task=task, configuration=config)


async def _validate(expectations: list[ExpectationSpec], adapter_result: AdapterResult, cell_dir: Path, redactor: Redactor | None = None):
    return await validate_cell(
        cell=_cell(expectations),
        adapter_result=adapter_result,
        cell_dir=cell_dir,
        evidence_prefix="cell::evidence",
        redactor=redactor,
    )


async def test_exit_code_expectation(tmp_path: Path) -> None:
    expectation = ExpectationSpec(type="exit_code", value=0)
    evaluation, _ = await _validate([expectation], AdapterResult(status=CellStatus.passed, exit_code=0), tmp_path)
    assert evaluation.pass_fail == "pass"
    evaluation, _ = await _validate([expectation], AdapterResult(status=CellStatus.passed, exit_code=2), tmp_path)
    assert evaluation.pass_fail == "fail"


async def test_contains_reads_stderr_stream(tmp_path: Path) -> None:
    expectation = ExpectationSpec(type="contains", value="warning", stream="stderr")
    evaluation, _ = await _validate(
        [expectation], AdapterResult(status=CellStatus.passed, stdout="", stderr="warning: deprecated"), tmp_path
    )
    assert evaluation.pass_fail == "pass"


async def test_file_exists_expectation(tmp_path: Path) -> None:
    (tmp_path / "result.txt").write_text("ok")
    evaluation, _ = await _validate(
        [ExpectationSpec(type="file_exists", value="result.txt")], AdapterResult(status=CellStatus.passed), tmp_path
    )
    assert evaluation.pass_fail == "pass"
    evaluation, _ = await _validate(
        [ExpectationSpec(type="file_exists", value="missing.txt")], AdapterResult(status=CellStatus.passed), tmp_path
    )
    assert evaluation.pass_fail == "fail"


async def test_file_exists_rejects_path_escape(tmp_path: Path) -> None:
    # A file outside the cell directory must never validate, even if it exists.
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("exists")
    cell_dir = tmp_path / "cell"
    cell_dir.mkdir()
    evaluation, _ = await _validate(
        [ExpectationSpec(type="file_exists", value="../outside.txt")], AdapterResult(status=CellStatus.passed), cell_dir
    )
    assert evaluation.pass_fail == "fail"


async def test_command_expectation_pass_and_fail(tmp_path: Path) -> None:
    ok = ExpectationSpec(type="command", command=[sys.executable, "-c", "raise SystemExit(0)"])
    evaluation, _ = await _validate([ok], AdapterResult(status=CellStatus.passed), tmp_path)
    assert evaluation.pass_fail == "pass"

    failing = ExpectationSpec(type="command", command=[sys.executable, "-c", "raise SystemExit(3)"])
    evaluation, _ = await _validate([failing], AdapterResult(status=CellStatus.passed), tmp_path)
    assert evaluation.pass_fail == "fail"
    assert "exit_code=3" in evaluation.comment


async def test_command_cwd_escape_is_rejected(tmp_path: Path) -> None:
    expectation = ExpectationSpec(type="command", command=[sys.executable, "-c", "pass"], cwd="../..")
    evaluation, _ = await _validate([expectation], AdapterResult(status=CellStatus.passed), tmp_path)
    assert evaluation.pass_fail == "fail"
    assert "escapes workspace directory" in evaluation.comment


async def test_command_not_found(tmp_path: Path) -> None:
    expectation = ExpectationSpec(type="command", command=["micro-eval-no-such-binary"])
    evaluation, _ = await _validate([expectation], AdapterResult(status=CellStatus.passed), tmp_path)
    assert evaluation.pass_fail == "fail"
    assert "not found" in evaluation.comment


async def test_command_output_is_redacted(tmp_path: Path) -> None:
    secret = "validator-secret-value"
    expectation = ExpectationSpec(type="command", command=[sys.executable, "-c", f"print('{secret}'); raise SystemExit(1)"])
    evaluation, evidence = await _validate(
        [expectation],
        AdapterResult(status=CellStatus.passed),
        tmp_path,
        redactor=Redactor({"MICRO_EVAL_SECRET_X": secret}),
    )
    assert secret not in evaluation.comment
    assert all(secret not in item.summary for item in evidence)
    assert "[REDACTED:MICRO_EVAL_SECRET_X]" in evaluation.comment


async def test_unsupported_expectation_type_fails(tmp_path: Path) -> None:
    evaluation, _ = await _validate(
        [ExpectationSpec(type="telepathy")], AdapterResult(status=CellStatus.passed), tmp_path
    )
    assert evaluation.pass_fail == "fail"
    assert "unsupported expectation type" in evaluation.comment


async def test_file_exists_observes_workspace_by_default(tmp_path: Path) -> None:
    # #13: file_exists must observe the workspace the agent ran in, not the
    # artifact output directory.
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    workspace.mkdir()
    output.mkdir()
    (workspace / "created.txt").write_text("written by agent")
    (output / "artifact.txt").write_text("collected output")

    evaluation, _ = await validate_cell(
        cell=_cell([ExpectationSpec(type="file_exists", value="created.txt")]),
        adapter_result=AdapterResult(status=CellStatus.passed),
        cell_dir=output,
        evidence_prefix="cell::evidence",
        workspace_dir=workspace,
    )
    assert evaluation.pass_fail == "pass"

    # An output-dir file is not in workspace scope by default.
    evaluation, _ = await validate_cell(
        cell=_cell([ExpectationSpec(type="file_exists", value="artifact.txt")]),
        adapter_result=AdapterResult(status=CellStatus.passed),
        cell_dir=output,
        evidence_prefix="cell::evidence",
        workspace_dir=workspace,
    )
    assert evaluation.pass_fail == "fail"


async def test_file_exists_output_dir_placeholder(tmp_path: Path) -> None:
    # #13: the {output_dir} placeholder opts into the artifact output directory.
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    workspace.mkdir()
    output.mkdir()
    (output / "artifact.txt").write_text("collected output")

    evaluation, _ = await validate_cell(
        cell=_cell([ExpectationSpec(type="file_exists", value="{output_dir}/artifact.txt")]),
        adapter_result=AdapterResult(status=CellStatus.passed),
        cell_dir=output,
        evidence_prefix="cell::evidence",
        workspace_dir=workspace,
    )
    assert evaluation.pass_fail == "pass"
