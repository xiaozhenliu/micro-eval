"""Build canonical RunPlan objects from project config and tasks."""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from pathlib import Path

from micro_eval import __version__
from micro_eval.models.configuration import ProjectConfigV2
from micro_eval.models.environment import ReplayCanonical, SameStartSnapshot
from micro_eval.models.ids import canonical_digest, compact_timestamp, new_run_id
from micro_eval.models.run import RunCell, RunPlan
from micro_eval.models.task import TaskSpec
from micro_eval.engine.workspace import build_same_start_snapshot


def build_run_plan(
    config: ProjectConfigV2,
    tasks: list[TaskSpec],
    *,
    max_concurrency: int | None = None,
    project_root: Path | str | None = None,
) -> RunPlan:
    """Expand tasks x configurations x repetitions into a RunPlan."""
    guardrails = config.guardrails.model_copy(deep=True)
    if max_concurrency is not None:
        guardrails.max_concurrency = max_concurrency

    run_id = new_run_id()
    created_at = datetime.now(timezone.utc).isoformat()
    cells: list[RunCell] = []
    for task in tasks:
        for configuration in config.configurations:
            for repetition in range(1, configuration.repetitions + 1):
                cell_id = f"{run_id}::{task.id}::{configuration.id}::rep-{repetition}"
                cells.append(
                    RunCell(
                        cell_id=cell_id,
                        task=task,
                        configuration=configuration,
                        repetition=repetition,
                    )
                )

    task_revisions = {task.id: task.revision_id for task in tasks}
    configuration_digests = {
        configuration.id: configuration.digest for configuration in config.configurations
    }
    guardrails_digest = canonical_digest(
        {
            "max_concurrency": guardrails.max_concurrency,
            "timeout_s": guardrails.timeout_s,
            "output_cap_bytes": guardrails.output_cap_bytes,
            "artifact_cap_bytes": guardrails.artifact_cap_bytes,
            "stop_on_cell_error": guardrails.stop_on_cell_error,
        }
    )
    snapshot = build_same_start_snapshot(
        project_root=project_root or Path.cwd(),
        tasks=tasks,
        config_hash=config.config_hash,
        configuration_digests=configuration_digests,
        task_revisions=task_revisions,
        python_version=platform.python_version(),
        guardrails_digest=guardrails_digest,
        timestamp=created_at,
    )
    workspace_fingerprint = canonical_digest(
        {
            "workspace_type": snapshot.workspace_type,
            "git_commit": snapshot.git_commit,
            "dirty": snapshot.dirty,
            "workspace_map": snapshot.workspace_map,
            "setup_commands_digest": snapshot.setup_commands_digest,
            "sandbox_resource_limits": snapshot.sandbox_resource_limits,
            "guardrails_digest": snapshot.guardrails_digest,
        }
    )
    replay = ReplayCanonical(
        tool_version=__version__,
        config_hash=config.config_hash,
        task_ids=[task.id for task in tasks],
        task_revisions=task_revisions,
        configuration_ids=[configuration.id for configuration in config.configurations],
        configuration_digests=configuration_digests,
        workspace_type=snapshot.workspace_type,
        git_commit=snapshot.git_commit,
        workspace_map=snapshot.workspace_map,
        workspace_fingerprint=workspace_fingerprint,
        setup_commands_digest=snapshot.setup_commands_digest,
        guardrails_digest=guardrails_digest,
        max_concurrency=guardrails.max_concurrency,
    )
    replay.digest = canonical_digest(
        {
            "tool_version": replay.tool_version,
            "config_hash": replay.config_hash,
            "task_ids": replay.task_ids,
            "task_revisions": replay.task_revisions,
            "configuration_ids": replay.configuration_ids,
            "configuration_digests": replay.configuration_digests,
            "workspace_fingerprint": replay.workspace_fingerprint,
            "guardrails_digest": replay.guardrails_digest,
            "max_concurrency": replay.max_concurrency,
            "setup_commands_digest": snapshot.setup_commands_digest,
        }
    )

    return RunPlan(
        run_id=run_id,
        project_name=config.project_name,
        created_at=created_at,
        output_dir=config.output_dir,
        guardrails=guardrails,
        trace=config.trace,
        judge=config.judge,
        cells=cells,
        config_hash=config.config_hash,
        migration_warnings=config.migration_warnings,
        same_start_snapshot=snapshot,
        replay_canonical=replay,
        denominator_policy=config.evaluation.denominator_policy,
    )


def plan_summary(plan: RunPlan) -> dict[str, object]:
    """Return a compact machine-readable plan summary."""
    return {
        "run_id": plan.run_id,
        "project_name": plan.project_name,
        "cell_count": len(plan.cells),
        "max_concurrency": plan.guardrails.max_concurrency,
        "tasks": sorted({cell.task.id for cell in plan.cells}),
        "configurations": sorted({cell.configuration.id for cell in plan.cells}),
        "replay_digest": plan.replay_canonical.digest if plan.replay_canonical else None,
    }


def compact_now() -> str:
    """Expose compact timestamp for tests and CLI display."""
    return compact_timestamp()
