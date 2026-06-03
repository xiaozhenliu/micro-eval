"""Deterministic validation helpers."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from micro_eval.engine.adapter import Redactor
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.ids import compact_timestamp, sha256_text
from micro_eval.models.run import AdapterResult, RunCell


async def validate_cell(
    *,
    cell: RunCell,
    adapter_result: AdapterResult,
    cell_dir: Path,
    evidence_prefix: str,
    redactor: Redactor | None = None,
) -> tuple[EvaluationResult, list[EvidenceItem]]:
    """Validate one cell with deterministic expectations."""
    redactor = redactor or Redactor({})
    checks: list[tuple[bool, str]] = []
    evidence: list[EvidenceItem] = []
    expectations = cell.task.expectations

    if not expectations:
        checks.append((adapter_result.status.value == "pass", "agent exited successfully"))

    for index, expectation in enumerate(expectations):
        ok, summary = await _evaluate_expectation(expectation, adapter_result, cell_dir, redactor)
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
        comment=redactor.redact("; ".join(summary for _ok, summary in checks))[:500],
        evidence_refs=[item.evidence_id for item in evidence],
        created_at=compact_timestamp(),
    )
    return evaluation, evidence


async def _evaluate_expectation(
    expectation,
    adapter_result: AdapterResult,
    cell_dir: Path,
    redactor: Redactor,
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
    if expectation.type == "file_exists":
        rel = "" if expectation.value is None else str(expectation.value)
        target = (cell_dir / rel).resolve()
        ok = _is_relative_to(target, cell_dir.resolve()) and target.exists()
        return ok, f"file_exists {rel}: {'present' if ok else 'missing'}"
    if expectation.type == "command":
        return await _run_validation_command(expectation, cell_dir, redactor)
    return False, f"unsupported expectation type: {expectation.type}"


def _stream_text(stream: str, adapter_result: AdapterResult) -> str:
    if stream == "stdout":
        return adapter_result.stdout
    if stream == "stderr":
        return adapter_result.stderr
    return adapter_result.output


async def _run_validation_command(expectation, cell_dir: Path, redactor: Redactor) -> tuple[bool, str]:
    command = expectation.command or []
    cwd = cell_dir
    if expectation.cwd:
        cwd_value = expectation.cwd.replace("{output_dir}", ".")
        candidate = (cell_dir / cwd_value).resolve()
        if not _is_relative_to(candidate, cell_dir.resolve()):
            return False, "validation command cwd escapes cell directory"
        cwd = candidate
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"}}
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=expectation.timeout_s)
        except asyncio.TimeoutError:
            proc.terminate()
            await proc.wait()
            return False, "validation command timed out"
    except FileNotFoundError as exc:
        return False, f"validation command not found: {exc}"
    summary = redactor.redact((stdout + stderr)[:1000].decode(errors="replace"))
    return proc.returncode == 0, f"validation command exit_code={proc.returncode}: {summary[:300]}"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
