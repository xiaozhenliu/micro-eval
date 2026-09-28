import json
"""Tests for run worker logic."""

import asyncio
import signal
from pathlib import Path

import pytest

from micro_eval.models.configuration import Guardrails
from micro_eval.config.loader import load_config, load_task_paths
from micro_eval.config.planner import build_run_plan
from micro_eval.engine.cell_lifecycle import FinalizedCell
from micro_eval.models.run import CellResult, CellStatus, RunPlan, RunRecord, RunStatus
from micro_eval.server.queue import QueueDB
from micro_eval.server.models import WorkspaceMeta
from micro_eval.server.worker import _attach_server_provenance, _persist_run_failure, worker_loop
from micro_eval.store.run_store import RunStore, RunStoreError

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    (root / "workspaces").mkdir()
    return root


def test_crash_recovery_completed(data_root):
    """If run.json exists with completed_at, recover as done."""
    db = QueueDB(data_root / "queue.db")
    result = db.enqueue("ws-test", "alice", '{"run_id": "run-1"}')
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")

    ws_dir = data_root / "workspaces" / "ws-test" / ".micro-eval" / "runs" / "run-1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "run.json").write_text('{"completed_at": "2026-01-01T00:00:00Z"}')

    def resolver(ws_id):
        return data_root / "workspaces" / ws_id

    recovered = db.recover_stale_jobs(resolver)
    assert len(recovered) == 1
    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "done"
    db.close()


def test_crash_recovery_interrupted(data_root):
    """If run.json doesn't exist, recover as failed."""
    db = QueueDB(data_root / "queue.db")
    result = db.enqueue("ws-test", "alice", '{"run_id": "run-1"}')
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")

    ws_dir = data_root / "workspaces" / "ws-test"
    ws_dir.mkdir(parents=True)

    def resolver(ws_id):
        return data_root / "workspaces" / ws_id

    recovered = db.recover_stale_jobs(resolver)
    assert len(recovered) == 1
    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "failed"
    assert "crashed" in recovered_job["error"]
    db.close()


def test_crash_recovery_with_cancel_requested(data_root):
    """If cancel was requested and run completed, recover as cancelled."""
    db = QueueDB(data_root / "queue.db")
    result = db.enqueue("ws-test", "alice", '{"run_id": "run-1"}')
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")
    db.request_cancel(job["job_id"], "bob")

    ws_dir = data_root / "workspaces" / "ws-test" / ".micro-eval" / "runs" / "run-1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "run.json").write_text('{"completed_at": "2026-01-01T00:00:00Z"}')

    def resolver(ws_id):
        return data_root / "workspaces" / ws_id

    recovered = db.recover_stale_jobs(resolver)
    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "cancelled"
    db.close()


def test_crash_recovery_preserves_failed_run_status(data_root):
    """A terminal failed run must not be recovered as a successful job."""
    db = QueueDB(data_root / "queue.db")
    db.enqueue("ws-test", "alice", '{"run_id": "run-1"}')
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")

    ws_dir = data_root / "workspaces" / "ws-test" / ".micro-eval" / "runs" / "run-1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "run.json").write_text(
        '{"status":"failed","completed_at":"2026-01-01T00:00:00Z",'
        '"failure_reason":"run timed out after 1s"}'
    )

    recovered = db.recover_stale_jobs(lambda ws_id: data_root / "workspaces" / ws_id)

    assert recovered == [job["job_id"]]
    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "failed"
    assert recovered_job["error"] == "run timed out after 1s"
    db.close()


def test_crash_recovery_reads_custom_output_directory(data_root):
    db = QueueDB(data_root / "queue.db")
    db.enqueue(
        "ws-test",
        "alice",
        '{"run_id":"run-1","output_dir":"custom/runs"}',
    )
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")

    run_dir = data_root / "workspaces" / "ws-test" / "custom" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        '{"status":"failed","completed_at":"2026-01-01T00:00:00Z",'
        '"failure_reason":"custom output failure"}'
    )

    db.recover_stale_jobs(lambda ws_id: data_root / "workspaces" / ws_id)

    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "failed"
    assert recovered_job["error"] == "custom output failure"
    db.close()


def test_crash_recovery_rejects_output_directory_escape(data_root):
    db = QueueDB(data_root / "queue.db")
    db.enqueue(
        "ws-test",
        "alice",
        '{"run_id":"run-1","output_dir":"../../outside"}',
    )
    job = db.dequeue_next()
    db.update_status(job["job_id"], "running", run_id="run-1")

    db.recover_stale_jobs(lambda ws_id: data_root / "workspaces" / ws_id)

    recovered_job = db.get_job(job["job_id"])
    assert recovered_job["status"] == "failed"
    assert recovered_job["error"] == "worker crashed with invalid run output directory"
    db.close()


def test_worker_provenance_is_present_in_initial_run_record(tmp_path):
    """Worker provenance reaches the first persisted run.json before execution."""
    job = {
        "job_id": "job-20260808T080000Z-12345678",
        "workspace_id": "ws-20260808T080000Z-12345678",
        "owner": "alice",
    }

    workspace_meta = WorkspaceMeta(
        workspace_id=job["workspace_id"],
        name="quickstart-workspace",
        owner="alice",
        template_id="quickstart-smoke",
        template_version="1.0.0",
        created_at="2026-08-08T08:00:00+00:00",
    )
    plan = RunPlan(
        run_id="run-20260808T080000Z-12345678",
        project_name="quickstart",
        created_at="2026-08-08T08:00:00+00:00",
        output_dir=".micro-eval/runs",
        guardrails=Guardrails(),
        cells=[],
        config_hash="config-hash",
    )

    enriched_plan = _attach_server_provenance(
        plan,
        job,
        workspace_meta,
        "team-eval-server",
    )
    store = RunStore(tmp_path)
    store.init_run(enriched_plan)

    run_path = store.run_dir(plan.run_id) / "run.json"
    persisted = RunRecord.model_validate_json(run_path.read_text())
    assert persisted.owner == "alice"
    assert persisted.server_context is not None
    assert persisted.server_context.workspace_id == job["workspace_id"]
    assert persisted.server_context.job_id == job["job_id"]
    assert persisted.server_context.template_id == "quickstart-smoke"
    assert persisted.server_context.template_version == "1.0.0"

    persisted.owner = "mallory"
    with pytest.raises(RunStoreError, match="immutable"):
        store.write_run(persisted)

    unchanged = store.read_run(plan.run_id)
    assert unchanged.owner == "alice"
    assert unchanged.server_context is not None
    assert unchanged.server_context.owner == "alice"

    tampered_context = unchanged.server_context.model_copy(update={"job_id": "job-tampered"})
    unchanged.server_context = tampered_context
    with pytest.raises(RunStoreError, match="immutable"):
        store.write_run(unchanged)

    still_unchanged = store.read_run(plan.run_id)
    assert still_unchanged.server_context is not None
    assert still_unchanged.server_context.job_id == job["job_id"]


def test_persist_run_failure_writes_terminal_status(tmp_path):
    plan = RunPlan(
        run_id="run-timeout",
        project_name="timeout-test",
        created_at="2026-08-08T08:00:00+00:00",
        output_dir=".micro-eval/runs",
        guardrails=Guardrails(),
        cells=[],
        config_hash="config-hash",
    )
    store = RunStore(tmp_path)
    store.init_run(plan)

    persisted = _persist_run_failure(tmp_path, plan, "run timed out after 1s")

    assert persisted is True
    record = store.read_run(plan.run_id)
    assert record.status == RunStatus.failed
    assert record.completed_at is not None
    assert record.failure_reason == "run timed out after 1s"


def test_persist_run_failure_initializes_missing_run_record(tmp_path):
    plan = RunPlan(
        run_id="missing-run",
        project_name="timeout-test",
        created_at="2026-08-08T08:00:00+00:00",
        output_dir=".micro-eval/runs",
        guardrails=Guardrails(),
        cells=[],
        config_hash="config-hash",
    )

    assert _persist_run_failure(tmp_path, plan, "run timed out") is True
    record = RunStore(tmp_path).read_run(plan.run_id)
    assert record.status == RunStatus.failed
    assert record.failure_reason == "run timed out"


async def test_worker_timeout_persists_queue_and_run_failure(data_root, monkeypatch):
    workspace_id = "ws-20260808T080000Z-12345678"
    workspace_path = data_root / "workspaces" / workspace_id
    workspace_path.mkdir(parents=True)
    # The resolver validates workspace.json (id must match the directory);
    # a real workspace always has it because WorkspaceManager.create writes it.
    (workspace_path / "workspace.json").write_text(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "name": "timeout-ws",
                "owner": "alice",
                "template_id": None,
                "template_version": None,
                "created_at": "2026-08-08T08:00:00+00:00",
                "description": "",
            }
        )
    )
    plan = RunPlan(
        run_id="run-timeout",
        project_name="timeout-test",
        created_at="2026-08-08T08:00:00+00:00",
        output_dir=".micro-eval/runs",
        guardrails=Guardrails(),
        cells=[],
        config_hash="config-hash",
    )
    setup_db = QueueDB(data_root / "queue.db")
    queued = setup_db.enqueue(workspace_id, "alice", plan.model_dump_json())
    setup_db.close()

    class BlockingKernel:
        def __init__(self, project_root, on_cell_complete=None, cancel_requested=None):
            self.store = RunStore(project_root)

        async def run(self, run_plan):
            self.store.init_run(run_plan)
            await asyncio.sleep(60)

    handlers = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop,
        "add_signal_handler",
        lambda sig, callback: handlers.setdefault(sig, callback),
    )
    monkeypatch.setattr("micro_eval.server.worker.ExecutionKernel", BlockingKernel)

    worker_task = asyncio.create_task(
        worker_loop(data_root, poll_interval=0.01, run_timeout=0.01)
    )
    for _ in range(100):
        await asyncio.sleep(0.01)
        inspect_db = QueueDB(data_root / "queue.db")
        job = inspect_db.get_job(queued["job_id"])
        inspect_db.close()
        if job["status"] == "failed":
            break
    else:
        raise AssertionError("worker did not persist timeout status")

    handlers[signal.SIGTERM]()
    await asyncio.wait_for(worker_task, timeout=1)

    assert job["error"] == "run timed out after 0.01s"
    record = RunStore(workspace_path).read_run(plan.run_id)
    assert record.status == RunStatus.failed
    assert record.completed_at is not None
    assert record.failure_reason == "run timed out after 0.01s"


async def test_worker_cancel_between_cells_keeps_partial_run(data_root, monkeypatch):
    workspace_id = "ws-20260808T080000Z-12345678"
    workspace_path = data_root / "workspaces" / workspace_id
    workspace_path.mkdir(parents=True)
    (workspace_path / "workspace.json").write_text(json.dumps({
        "workspace_id": workspace_id,
        "name": "cancel-ws",
        "owner": "alice",
        "template_id": None,
        "template_version": None,
        "created_at": "2026-08-08T08:00:00+00:00",
        "description": "",
    }))
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    config.output_dir = ".micro-eval/runs"
    plan = build_run_plan(config, tasks, max_concurrency=1)
    assert len(plan.cells) == 3
    plan.denominator_policy = "exclude_failed"
    assert plan.evaluation_contract is not None
    plan.evaluation_contract.denominator_policy = "exclude_failed"

    setup_db = QueueDB(data_root / "queue.db")
    queued = setup_db.enqueue(workspace_id, "alice", plan.model_dump_json())
    setup_db.close()

    started = asyncio.Event()
    release = asyncio.Event()
    executed: list[str] = []

    async def run_cell(self, cell, lifecycle, record):
        executed.append(cell.cell_id)
        started.set()
        await release.wait()
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

    monkeypatch.setattr("micro_eval.engine.kernel.ExecutionKernel._run_cell", run_cell)
    handlers = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", lambda sig, callback: handlers.setdefault(sig, callback))
    worker_task = asyncio.create_task(worker_loop(data_root, poll_interval=0.01))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        cancel_db = QueueDB(data_root / "queue.db")
        try:
            assert cancel_db.request_cancel(queued["job_id"], "bob")["status"] == "running"
        finally:
            cancel_db.close()
        release.set()
        for _ in range(100):
            await asyncio.sleep(0.01)
            inspect_db = QueueDB(data_root / "queue.db")
            job = inspect_db.get_job(queued["job_id"])
            inspect_db.close()
            if job["status"] == "cancelled":
                break
        else:
            raise AssertionError("worker did not finish cancelled job")
    finally:
        release.set()
        handlers[signal.SIGTERM]()
        await asyncio.wait_for(worker_task, timeout=1)

    assert executed == [plan.cells[0].cell_id]
    assert job["finished_at"] is not None
    assert job["progress"]["completed_cells"] == 1
    assert job["progress"]["total_cells"] == 3
    store = RunStore(workspace_path)
    run_path = store.run_dir(plan.run_id) / "run.json"
    assert json.loads(run_path.read_text())["status"] == "cancelled"
    record = store.read_run(plan.run_id)
    assert record.status == RunStatus.cancelled
    assert len(record.results) == 1
    assert record.results[0].cell_id == plan.cells[0].cell_id
    assert (run_path.parent / "cells" / plan.cells[0].cell_id / "result.json").exists()
    assert record.decision is not None
    assert record.decision.verdict.value == "inconclusive"
    stats = record.decision.aggregation.per_configuration[plan.cells[0].configuration.id]
    assert stats.denominator_policy == "exclude_failed"
    assert stats.n_cells == 1
