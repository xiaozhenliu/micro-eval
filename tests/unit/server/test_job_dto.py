"""Public job DTO contracts for both queue read paths."""

from micro_eval.server.models import JobDTO
from micro_eval.server.queue import QueueDB


def test_job_and_dashboard_return_the_same_structured_progress(tmp_path):
    db = QueueDB(tmp_path / "queue.db")
    try:
        done = db.enqueue("ws-1", "alice", '{"run_id":"r1"}')
        running = db.enqueue("ws-1", "bob", '{"run_id":"r2"}')
        queued = db.enqueue("ws-1", "carol", '{"run_id":"r3"}')

        assert db.dequeue_next()["job_id"] == done["job_id"]
        done_progress = {
            "completed_cells": 4,
            "total_cells": 4,
            "current_task": "task-4",
            "current_config": "config-a",
        }
        db.update_progress(done["job_id"], done_progress)
        assert db.finish_running(done["job_id"]) == "done"

        assert db.dequeue_next()["job_id"] == running["job_id"]
        running_progress = {
            "completed_cells": 1,
            "total_cells": 4,
            "current_task": "task-1",
            "current_config": "config-a",
        }
        db.update_progress(running["job_id"], running_progress)

        dashboard = db.get_queue_dashboard()
        assert dashboard["running"]["progress"] == db.get_job(running["job_id"])["progress"] == running_progress
        assert dashboard["recent_completed"][0]["progress"] == db.get_job(done["job_id"])["progress"] == done_progress
        assert dashboard["queued"][0]["job_id"] == queued["job_id"]
        assert dashboard["queued"][0]["progress"] is None
        assert dashboard["queued"][0]["position"] == 1

        for section in (dashboard["running"], *dashboard["queued"], *dashboard["recent_completed"]):
            JobDTO.model_validate(section)
    finally:
        db.close()


def test_job_dto_public_fields_match_queue_contract():
    assert set(JobDTO.model_fields) == {
        "job_id", "workspace_id", "owner", "status", "enqueued_at",
        "started_at", "finished_at", "run_id", "error", "progress",
        "cancel_requested_at", "cancelled_by", "position",
    }
