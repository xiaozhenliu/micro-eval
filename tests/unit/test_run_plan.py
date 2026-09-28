"""Acceptance tests for RunPlan expansion."""

from pathlib import Path

from micro_eval.config.loader import load_config, load_task_paths
from micro_eval.config.planner import build_run_plan

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_matrix_config_expands_tasks_configurations_repetitions():
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)

    plan = build_run_plan(config, tasks, max_concurrency=3)

    assert len(plan.cells) == 3
    assert plan.guardrails.max_concurrency == 3
    assert plan.replay_canonical is not None
    assert plan.replay_canonical.digest
    assert all(cell.cell_id.startswith(plan.run_id) for cell in plan.cells)


def test_replay_digest_includes_guardrails_digest():
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    first = build_run_plan(config, tasks)
    changed = config.model_copy(deep=True)
    changed.guardrails.timeout_s = config.guardrails.timeout_s + 1
    changed.config_hash = config.config_hash
    second = build_run_plan(changed, tasks)

    assert first.same_start_snapshot is not None
    assert second.same_start_snapshot is not None
    assert first.replay_canonical is not None
    assert second.replay_canonical is not None
    assert first.same_start_snapshot.guardrails_digest != second.same_start_snapshot.guardrails_digest
    assert first.replay_canonical.guardrails_digest != second.replay_canonical.guardrails_digest
    assert first.replay_canonical.digest != second.replay_canonical.digest


def test_legacy_config_bridge_expands_to_two_configurations():
    config_path = FIXTURES / "configs" / "eval_legacy.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    plan = build_run_plan(config, tasks)

    assert [configuration.id for configuration in config.configurations] == ["baseline", "candidate"]
    assert len(plan.cells) == 2
    assert config.migration_warnings
