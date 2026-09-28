"""Tests for QueueDB."""

import pytest

import threading

from micro_eval.server.queue import QueueDB, QueueFullError


@pytest.fixture
def queue(tmp_path):
    db = QueueDB(tmp_path / "queue.db")
    yield db
    db.close()


def test_enqueue_creates_job(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    assert result["status"] == "queued"
    assert result["job_id"].startswith("job-")


def test_dequeue_fifo(queue):
    queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.enqueue("ws-2", "bob", '{"run_id": "r2"}')
    job = queue.dequeue_next()
    assert job["owner"] == "alice"
    job2 = queue.dequeue_next()
    assert job2["owner"] == "bob"


def test_dequeue_empty(queue):
    assert queue.dequeue_next() is None


def test_job_lifecycle(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    job_id = result["job_id"]
    job = queue.dequeue_next()
    assert job["status"] == "running"
    queue.update_status(job_id, "done", finished_at="2026-01-01T00:00:00Z")
    done_job = queue.get_job(job_id)
    assert done_job["status"] == "done"


def test_cancel_queued_job(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    job_id = result["job_id"]
    cancel_result = queue.request_cancel(job_id, "bob")
    assert cancel_result["status"] == "cancelled"
    job = queue.get_job(job_id)
    assert job["status"] == "cancelled"
    assert job["cancelled_by"] == "bob"


def test_cancel_running_job_is_honoured_on_completion(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    job_id = result["job_id"]
    queue.dequeue_next()
    cancel_result = queue.request_cancel(job_id, "bob")
    assert cancel_result["status"] == "running"
    assert cancel_result["cancel_requested_at"] is not None
    assert queue.is_cancel_requested(job_id)
    assert queue.finish_running(job_id) == "cancelled"
    finished = queue.get_job(job_id)
    assert finished["status"] == "cancelled"
    assert finished["finished_at"] is not None


def test_finish_running_without_cancel_is_done(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.dequeue_next()
    assert queue.finish_running(result["job_id"]) == "done"
    assert queue.get_job(result["job_id"])["finished_at"] is not None


def test_cancel_does_not_mark_job_after_worker_finishes(queue, monkeypatch):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.dequeue_next()
    get_job = queue.get_job
    first_read = True

    def read_during_finish(job_id):
        nonlocal first_read
        job = get_job(job_id)
        if first_read:
            first_read = False
            assert queue.finish_running(job_id) == "done"
        return job

    monkeypatch.setattr(queue, "get_job", read_during_finish)
    assert queue.request_cancel(result["job_id"], "bob") == {
        "error": "job_already_terminated", "status": "done",
    }
    finished = get_job(result["job_id"])
    assert finished["cancel_requested_at"] is None


def test_cancel_done_job_rejected(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.dequeue_next()
    queue.update_status(result["job_id"], "done", finished_at="2026-01-01T00:00:00Z")
    cancel_result = queue.request_cancel(result["job_id"], "bob")
    assert cancel_result["error"] == "job_already_terminated"


def test_queue_overflow(queue):
    for i in range(3):
        queue.enqueue(f"ws-{i}", "alice", f'{{"run_id": "r{i}"}}', max_queue_size=3)
    with pytest.raises(QueueFullError):
        queue.enqueue("ws-x", "alice", '{"run_id": "rx"}', max_queue_size=3)


def test_progress_update(queue):
    result = queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.dequeue_next()
    queue.update_progress(result["job_id"], {"completed_cells": 3, "total_cells": 12})
    job = queue.get_job(result["job_id"])
    assert job["progress"]["completed_cells"] == 3


def test_has_pending_jobs(queue):
    queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    assert queue.has_pending_jobs("ws-1")
    assert not queue.has_pending_jobs("ws-other")


def test_queue_dashboard(queue):
    queue.enqueue("ws-1", "alice", '{"run_id": "r1"}')
    queue.enqueue("ws-2", "bob", '{"run_id": "r2"}')
    queue.dequeue_next()
    dashboard = queue.get_queue_dashboard()
    assert dashboard["running"]["owner"] == "alice"
    assert len(dashboard["queued"]) == 1
    assert dashboard["queued"][0]["position"] == 1


def test_capacity_check_and_insert_are_one_transaction(tmp_path):
    # Round-9 review: many connections racing for the last slot must admit
    # exactly max_queue_size jobs, never more.
    db_path = tmp_path / "queue.db"
    QueueDB(db_path).close()
    results: list[str] = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def worker(index: int) -> None:
        db = QueueDB(db_path)
        try:
            start.wait()
            try:
                db.enqueue(f"ws-{index}", "alice", "{}", max_queue_size=3)
                outcome = "ok"
            except QueueFullError:
                outcome = "full"
        finally:
            db.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 3
    assert results.count("full") == 5


def test_enqueue_refusal_leaves_no_open_transaction(tmp_path):
    db = QueueDB(tmp_path / "queue.db")
    try:
        db.enqueue("ws-a", "alice", "{}", max_queue_size=1)
        with pytest.raises(QueueFullError):
            db.enqueue("ws-b", "alice", "{}", max_queue_size=1)
        assert db.has_pending_jobs("ws-a") is True
        assert db.has_pending_jobs("ws-b") is False
    finally:
        db.close()


def test_queue_db_is_owner_only(tmp_path):
    import stat as _stat

    db = QueueDB(tmp_path / "queue.db")
    db.close()
    assert _stat.S_IMODE((tmp_path / "queue.db").stat().st_mode) == 0o600
