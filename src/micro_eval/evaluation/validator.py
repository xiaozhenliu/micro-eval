"""Deterministic validation helpers."""

from __future__ import annotations

import os
import posixpath
from pathlib import Path
from typing import TYPE_CHECKING

from micro_eval.engine.adapter import Redactor
from micro_eval.engine.command import resolve_command_argv
from micro_eval.engine.process_runner import run_process
from micro_eval.engine.providers.base import ExecutionRequest
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.ids import compact_timestamp, rubric_digest, sha256_text
from micro_eval.models.run import AdapterResult, RunCell
from micro_eval.models.task import ExpectationSpec

if TYPE_CHECKING:
    from micro_eval.engine.execution import ExecutionContext


async def validate_cell(
    *,
    cell: RunCell,
    adapter_result: AdapterResult,
    cell_dir: Path,
    evidence_prefix: str,
    redactor: Redactor | None = None,
    workspace_dir: Path | None = None,
    execution_context: ExecutionContext | None = None,
    execution_available: bool = True,
) -> tuple[EvaluationResult, list[EvidenceItem]]:
    """Validate one cell with deterministic expectations.

    ``file_exists`` and ``command`` expectations observe the agent's workspace
    (``workspace_dir``) by default, since that is where the agent actually runs
    and mutates files. Expectations may opt into the artifact output directory
    with the ``{output_dir}`` placeholder. When ``workspace_dir`` is omitted the
    output directory doubles as the execution scope (ad-hoc/legacy callers).
    An ``execution_context`` takes precedence over ``workspace_dir`` and routes
    workspace observations and commands through that provider. File checks in
    ``{output_dir}`` inspect collected artifacts; commands use the provider's
    output path and Python executable.
    If workspace preparation failed or cleanup already ran, callers set
    ``execution_available=False`` to retain only pure exit/text checks.
    """
    redactor = redactor or Redactor({})
    checks: list[tuple[bool, str]] = []
    evidence: list[EvidenceItem] = []
    expectations = cell.task.expectations
    exec_dir = (
        execution_context.workspace_path
        if execution_context is not None
        else workspace_dir if workspace_dir is not None else cell_dir
    )

    if not expectations:
        checks.append((adapter_result.status.value == "pass", "agent exited successfully"))

    for index, expectation in enumerate(expectations):
        ok, summary = await _evaluate_expectation(
            expectation, adapter_result, exec_dir, cell_dir, redactor, execution_context,
            execution_available,
        )
        checks.append((ok, summary))
        evidence.append(
            EvidenceItem(
                evidence_id=f"{evidence_prefix}::expectation-{index}",
                kind="validation",
                cell_id=cell.cell_id,
                status="passed" if ok else "failed",
                severity="info" if ok else "warning",
                summary=redactor.redact(summary)[:500],
                metadata={"passed": ok, "expectation_type": expectation.type},
            )
        )

    if not evidence:
        ok = all(item[0] for item in checks)
        evidence.append(
            EvidenceItem(
                evidence_id=f"{evidence_prefix}::exit-status",
                kind="validation",
                cell_id=cell.cell_id,
                status="passed" if ok else "failed",
                severity="info" if ok else "warning",
                summary="agent process completed" if ok else "agent process did not complete successfully",
                metadata={"passed": ok, "exit_code": adapter_result.exit_code},
            )
        )

    passed = all(ok for ok, _summary in checks) if checks else adapter_result.status.value == "pass"
    evaluation_id = f"{cell.cell_id}::validator::{sha256_text(str(checks))[:12]}"
    evaluation = EvaluationResult(
        evaluation_id=evaluation_id,
        cell_id=cell.cell_id,
        evaluator_type="validator",
        evaluator="micro-eval-deterministic-validator",
        pass_fail="pass" if passed else "fail",
        score=1.0 if passed else 0.0,
        rubric_hash=rubric_digest(cell.task.rubric),
        comment=redactor.redact("; ".join(summary for _ok, summary in checks))[:500],
        evidence_refs=[item.evidence_id for item in evidence],
        created_at=compact_timestamp(),
    )
    return evaluation, evidence


async def _evaluate_expectation(
    expectation: ExpectationSpec,
    adapter_result: AdapterResult,
    workspace_dir: Path,
    output_dir: Path,
    redactor: Redactor,
    execution_context: ExecutionContext | None = None,
    execution_available: bool = True,
) -> tuple[bool, str]:
    if expectation.type == "exit_code":
        expected = int(expectation.value if expectation.value is not None else 0)
        ok = adapter_result.exit_code == expected
        return ok, f"exit_code expected {expected}, got {adapter_result.exit_code}"
    if expectation.type == "contains":
        haystack = _stream_text(expectation.stream, adapter_result)
        needle = "" if expectation.value is None else str(expectation.value)
        ok = needle in haystack
        return ok, f"{expectation.stream} contains expected text" if ok else f"{expectation.stream} missing expected text"
    if expectation.type in {"file_exists", "command"} and not execution_available:
        return False, "validation unavailable: execution workspace was not prepared or has been cleaned up"
    if expectation.type == "file_exists":
        rel = "" if expectation.value is None else str(expectation.value)
        execution_output = execution_context.output_path if execution_context is not None else output_dir
        if "{output_dir}" in rel and execution_output is None:
            return False, "validation unavailable: execution output directory was not prepared"
        base, rel_path = _scope_base(rel, workspace_dir, execution_output or output_dir)
        # Observe what the agent wrote, including files that its output mode
        # did not select for export into the sanitized host artifact directory.
        remote = execution_context is not None and execution_context.is_remote
        target = _scoped_path(base, rel_path, remote=remote)
        if target is None:
            return False, f"file_exists {rel}: path escapes workspace directory"
        try:
            if execution_context is not None:
                ok = await execution_context.path_exists(target)
            else:
                ok = target.exists()
        except Exception as exc:
            return False, redactor.redact(f"file_exists {rel}: provider check failed: {exc}")
        return ok, f"file_exists {rel}: {'present' if ok else 'missing'}"
    if expectation.type == "command":
        if adapter_result.timed_out:
            return False, "validation command skipped because agent execution timed out"
        return await _run_validation_command(expectation, workspace_dir, output_dir, redactor, execution_context)
    return False, f"unsupported expectation type: {expectation.type}"


def _scope_base(raw: str, workspace_dir: Path, output_dir: Path) -> tuple[Path, str]:
    """Resolve a path/cwd expression to its scope base and relative remainder.

    The ``{output_dir}`` placeholder opts into the artifact output directory;
    every other expression is scoped to the agent's workspace, matching where
    the agent actually executed.
    """
    if "{output_dir}" in raw:
        return output_dir, raw.replace("{output_dir}", ".")
    return workspace_dir, raw


def _stream_text(stream: str, adapter_result: AdapterResult) -> str:
    if stream == "stdout":
        return adapter_result.stdout
    if stream == "stderr":
        return adapter_result.stderr
    return adapter_result.output


async def _run_validation_command(
    expectation: ExpectationSpec,
    workspace_dir: Path,
    output_dir: Path,
    redactor: Redactor,
    execution_context: ExecutionContext | None = None,
) -> tuple[bool, str]:
    execution_output = execution_context.output_path if execution_context is not None else output_dir
    uses_output = any("{output_dir}" in arg for arg in expectation.command or []) or (
        "{output_dir}" in (expectation.cwd or "")
    )
    if uses_output and execution_output is None:
        return False, "validation command output directory is unavailable in the execution environment"
    replacements = {"{output_dir}": str(execution_output)} if execution_output is not None else {}
    if execution_context is not None:
        replacements["{python}"] = execution_context.python_executable
    command = resolve_command_argv(
        expectation.command or [],
        replacements=replacements,
    )
    cwd = workspace_dir
    if expectation.cwd:
        base, cwd_value = _scope_base(expectation.cwd, workspace_dir, execution_output or output_dir)
        candidate = _scoped_path(
            base, cwd_value, remote=execution_context is not None and execution_context.is_remote
        )
        if candidate is None:
            return False, "validation command cwd escapes workspace directory"
        cwd = candidate
    # Remote providers use their own environment; host paths and credentials
    # must not become overrides in a container or VM.
    env = {} if execution_context is not None and execution_context.is_remote else {
        key: value for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
    }
    request = ExecutionRequest(argv=command, cwd=cwd, env=env, timeout_s=expectation.timeout_s)
    try:
        result = (
            await execution_context.execute(request)
            if execution_context is not None
            else await run_process(request)
        )
    except FileNotFoundError as exc:
        return False, redactor.redact(f"validation command not found: {exc}")
    except Exception as exc:
        return False, redactor.redact(f"validation command execution failed: {exc}")
    if result.timed_out:
        return False, "validation command timed out"
    summary = redactor.redact(result.stdout + result.stderr)[:300]
    return result.exit_code == 0, f"validation command exit_code={result.exit_code}: {summary}"


def _scoped_path(base: Path, value: str, *, remote: bool) -> Path | None:
    """Check provider paths lexically and local paths after resolving links."""
    if remote:
        parent = Path(posixpath.normpath(str(base)))
        target = Path(posixpath.normpath(str(base / value)))
    else:
        parent = base.resolve()
        target = (base / value).resolve()
    return target if _is_relative_to(target, parent) else None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
