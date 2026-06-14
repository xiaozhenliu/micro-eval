"""Per-cell error isolation (#14): one bad cell must not abort the run."""

import asyncio
from pathlib import Path

import pytest

from micro_eval.config.loader import load_config, load_task_paths
from micro_eval.config.planner import build_run_plan
from micro_eval.engine import kernel as kernel_module
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.run import CellStatus

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _build_plan(tmp_path):
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    config.output_dir = ".micro-eval/runs"
    return build_run_plan(config, tasks, max_concurrency=2)


def test_unexpected_cell_error_does_not_abort_run(tmp_path, monkeypatch):
    plan = _build_plan(tmp_path)
    target = plan.cells[0].cell_id
    real_validate = kernel_module.validate_cell

    async def flaky_validate(*, cell, **kwargs):
        # Inject an unexpected (non-Workspace/Adapter) error in post-invoke work.
        if cell.cell_id == target:
            raise RuntimeError("boom in post-invoke work")
        return await real_validate(cell=cell, **kwargs)

    monkeypatch.setattr(kernel_module, "validate_cell", flaky_validate)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    # Acceptance: the run record is finalized and persisted even with a bad cell.
    run_dir = tmp_path / ".micro-eval" / "runs" / plan.run_id
    assert (run_dir / "run.json").exists()
    assert len(record.results) == len(plan.cells)

    by_id = {result.cell_id: result for result in record.results}
    bad = by_id[target]
    assert bad.status == CellStatus.error
    assert bad.failure_mode == "kernel_error:RuntimeError"

    # Acceptance: sibling cells complete normally.
    siblings = [result for cell_id, result in by_id.items() if cell_id != target]
    assert siblings
    assert all(result.status != CellStatus.error for result in siblings)


def test_isolated_failure_redacts_secrets_in_stderr(tmp_path, monkeypatch):
    # Security: the fallback error result must not leak declared secrets via stderr_summary.
    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "supersecret-value")
    plan = _build_plan(tmp_path)
    target = plan.cells[0].cell_id
    real_validate = kernel_module.validate_cell

    async def leaky_validate(*, cell, **kwargs):
        if cell.cell_id == target:
            raise RuntimeError("failed handling supersecret-value in path")
        return await real_validate(cell=cell, **kwargs)

    monkeypatch.setattr(kernel_module, "validate_cell", leaky_validate)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    bad = {result.cell_id: result for result in record.results}[target]
    assert "supersecret-value" not in bad.stderr_summary
    assert "[REDACTED:MICRO_EVAL_SECRET_TOKEN]" in bad.stderr_summary


def test_cancelled_error_propagates_not_isolated(tmp_path, monkeypatch):
    # The isolation boundary must re-raise CancelledError, never swallow it,
    # so timeout / Ctrl-C cancellation semantics keep working.
    plan = _build_plan(tmp_path)
    target = plan.cells[0].cell_id
    real_validate = kernel_module.validate_cell

    async def cancelling_validate(*, cell, **kwargs):
        if cell.cell_id == target:
            raise asyncio.CancelledError()
        return await real_validate(cell=cell, **kwargs)

    monkeypatch.setattr(kernel_module, "validate_cell", cancelling_validate)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ExecutionKernel(tmp_path).run(plan))
