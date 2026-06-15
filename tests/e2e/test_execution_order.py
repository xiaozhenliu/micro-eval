"""Execution-order recording and opt-in randomization (P3)."""

import asyncio
from pathlib import Path

from micro_eval.config.loader import load_config, load_task_paths
from micro_eval.config.planner import build_run_plan
from micro_eval.engine.kernel import ExecutionKernel

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _plan(tmp_path):
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    config.output_dir = ".micro-eval/runs"
    return build_run_plan(config, tasks, max_concurrency=2)


def test_execution_order_recorded_in_plan_order_by_default(tmp_path):
    plan = _plan(tmp_path)
    expected = [cell.cell_id for cell in plan.cells]

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    # Default keeps deterministic plan order and records no seed.
    assert record.execution_order == expected
    assert record.execution_seed is None


def test_execution_order_randomized_records_seed_and_permutation(tmp_path):
    plan = _plan(tmp_path)
    plan.guardrails.randomize_execution_order = True
    cell_ids = {cell.cell_id for cell in plan.cells}

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    # A seed is recorded and the order is a permutation of the planned cells
    # (same set, same length) — reproducible from the recorded seed.
    assert record.execution_seed is not None
    assert set(record.execution_order) == cell_ids
    assert len(record.execution_order) == len(plan.cells)
    # Every planned cell still ran.
    assert {result.cell_id for result in record.results} == cell_ids
