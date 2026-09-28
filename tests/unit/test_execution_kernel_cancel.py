"""Cancellation boundaries for the bounded cell dispatcher."""

import asyncio
from pathlib import Path

import pytest

from micro_eval.config.loader import load_config, load_task_paths
from micro_eval.config.planner import build_run_plan
from micro_eval.engine.cell_lifecycle import FinalizedCell
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.run import CellResult, CellStatus, RunStatus
from micro_eval.store.run_store import RunStore

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_cancel_drains_in_flight_cell_without_dispatching_third(tmp_path, monkeypatch):
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    config.output_dir = ".micro-eval/runs"
    plan = build_run_plan(config, tasks, max_concurrency=2)
    assert len(plan.cells) == 3

    second_started = asyncio.Event()
    release_second = asyncio.Event()
    started: list[str] = []
    cancelled = False

    async def run_cell(self, cell, lifecycle, record):
        started.append(cell.cell_id)
        if cell.cell_id == plan.cells[0].cell_id:
            await second_started.wait()
        else:
            second_started.set()
            await release_second.wait()
        return FinalizedCell(result=CellResult(
            cell_id=cell.cell_id,
            run_id=record.id,
            task_id=cell.task.id,
            configuration_id=cell.configuration.id,
            configuration_name=cell.configuration.name,
            repetition=cell.repetition,
            status=CellStatus.passed,
            score=1.0,
            pass_fail="pass",
        ), evaluations=())

    def on_complete(completed, total, result):
        nonlocal cancelled
        if completed == 1:
            cancelled = True
            release_second.set()

    monkeypatch.setattr(ExecutionKernel, "_run_cell", run_cell)
    record = await ExecutionKernel(
        tmp_path,
        on_cell_complete=on_complete,
        cancel_requested=lambda: cancelled,
    ).run(plan)

    assert started == [cell.cell_id for cell in plan.cells[:2]]
    assert record.execution_order == started
    assert len(record.results) == 2
    assert record.status == RunStatus.cancelled
    assert len(RunStore(tmp_path).read_run(plan.run_id).results) == 2
