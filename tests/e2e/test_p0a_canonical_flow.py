"""P0-a canonical execution flow tests."""

from pathlib import Path

from micro_eval.config.loader import load_config, load_task_paths
from micro_eval.config.planner import build_run_plan
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.run import RunStatus

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_p0a_kernel_writes_canonical_run_layout(tmp_path):
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    config.output_dir = ".micro-eval/runs"
    plan = build_run_plan(config, tasks, max_concurrency=2)

    record = __import__("asyncio").run(ExecutionKernel(tmp_path).run(plan))

    run_dir = tmp_path / ".micro-eval" / "runs" / plan.run_id
    assert record.status == RunStatus.completed
    assert (run_dir / "run.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert len(record.results) == 3
    for cell_id in record.cells:
        cell_dir = run_dir / "cells" / cell_id
        assert (cell_dir / "result.json").exists()
        assert (cell_dir / "stdout.txt").exists()
        assert (cell_dir / "stderr.txt").exists()
        assert (cell_dir / "evaluation.json").exists()
    assert record.decision is not None
    assert record.decision.verdict.value in {"inconclusive", "needs_human_review"}
