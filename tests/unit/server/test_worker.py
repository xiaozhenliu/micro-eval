"""Tests for run worker logic."""

import pytest

from micro_eval.models.configuration import Guardrails
from micro_eval.models.run import RunPlan, RunRecord
from micro_eval.server.queue import QueueDB
from micro_eval.server.models import WorkspaceMeta
from micro_eval.server.worker import _attach_server_provenance
from micro_eval.store.run_store import RunStore, RunStoreError


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
