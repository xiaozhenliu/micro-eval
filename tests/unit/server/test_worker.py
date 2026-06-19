"""Tests for run worker logic."""

import pytest

from micro_eval.server.queue import QueueDB


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
