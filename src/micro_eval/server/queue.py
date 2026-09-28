"""SQLite-backed serial run queue for server mode."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import new_job_id


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class QueueDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        # Plans are stored verbatim; keep the database owner-only (best effort).
        for suffix in ("", "-wal", "-shm"):
            try:
                os.chmod(f"{self.db_path}{suffix}", 0o600)
            except OSError:
                pass
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id       TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                owner        TEXT NOT NULL,
                plan_json    TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'queued',
                enqueued_at  TEXT NOT NULL,
                started_at   TEXT,
                finished_at  TEXT,
                run_id       TEXT,
                error        TEXT,
                progress     TEXT,
                cancel_requested_at TEXT,
                cancelled_by TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_workspace ON jobs(workspace_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_enqueued ON jobs(enqueued_at);
        """)

    def enqueue(
        self,
        workspace_id: str,
        owner: str,
        plan_json: str,
        max_queue_size: int = 100,
    ) -> dict:
        # The capacity check and the insert must be one write transaction:
        # BEGIN IMMEDIATE takes the database write lock up front, so two
        # processes enqueueing at once cannot both see "one slot left"
        # (round-9 review, 2026-09-13).
        if self._conn.in_transaction:
            self._conn.commit()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status IN ('queued', 'running')"
            )
            count = cur.fetchone()["cnt"]
            if count >= max_queue_size:
                raise QueueFullError(count, max_queue_size)

            job_id = new_job_id()
            now = _utcnow()
            self._conn.execute(
                """INSERT INTO jobs (job_id, workspace_id, owner, plan_json, status, enqueued_at)
                   VALUES (?, ?, ?, ?, 'queued', ?)""",
                (job_id, workspace_id, owner, plan_json, now),
            )
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

        position = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'queued' AND enqueued_at <= ?",
            (now,),
        ).fetchone()["cnt"]
        return {"job_id": job_id, "status": "queued", "position": position}

    def dequeue_next(self) -> dict | None:
        cur = self._conn.execute(
            """UPDATE jobs SET status = 'running', started_at = ?
               WHERE job_id = (
                   SELECT job_id FROM jobs WHERE status = 'queued'
                   ORDER BY enqueued_at LIMIT 1
               ) RETURNING *""",
            (_utcnow(),),
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            return None
        return dict(row)

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        started_at: str | None = None,
        finished_at: str | None = None,
        run_id: str | None = None,
        error: str | None = None,
    ) -> None:
        sets = ["status = ?"]
        params: list = [status]
        if started_at:
            sets.append("started_at = ?")
            params.append(started_at)
        if finished_at:
            sets.append("finished_at = ?")
            params.append(finished_at)
        if run_id:
            sets.append("run_id = ?")
            params.append(run_id)
        if error:
            sets.append("error = ?")
            params.append(error)
        params.append(job_id)
        self._conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?", params)
        self._conn.commit()

    def update_progress(self, job_id: str, progress: dict) -> None:
        self._conn.execute(
            "UPDATE jobs SET progress = ? WHERE job_id = ?",
            (json.dumps(progress), job_id),
        )
        self._conn.commit()

    def finish_running(self, job_id: str) -> str:
        """Atomically finish a run without losing a concurrent cancel request."""
        row = self._conn.execute(
            """UPDATE jobs SET
                   status = CASE WHEN cancel_requested_at IS NULL THEN 'done' ELSE 'cancelled' END,
                   finished_at = ?
               WHERE job_id = ? AND status = 'running' RETURNING status""",
            (_utcnow(), job_id),
        ).fetchone()
        self._conn.commit()
        if row is None:
            raise RuntimeError(f"running job not found: {job_id}")
        return row["status"]

    def request_cancel(self, job_id: str, cancelled_by: str) -> dict | None:
        # A queued job can become running, or a running job can finish, between
        # the read and write. Only update the state actually observed.
        for _ in range(3):
            row = self.get_job(job_id)
            if row is None:
                return None
            status = row["status"]
            if status in ("done", "failed", "cancelled"):
                return {"error": "job_already_terminated", "status": status}
            now = _utcnow()
            if status == "queued":
                updated = self._conn.execute(
                    """UPDATE jobs SET status = 'cancelled', cancel_requested_at = ?,
                       cancelled_by = ?, finished_at = ?
                       WHERE job_id = ? AND status = 'queued' RETURNING job_id""",
                    (now, cancelled_by, now, job_id),
                ).fetchone()
                self._conn.commit()
                if updated is not None:
                    return {"job_id": job_id, "status": "cancelled", "cancel_requested_at": now}
            else:
                # The kernel checks this marker before each cell dispatch.
                updated = self._conn.execute(
                    """UPDATE jobs SET cancel_requested_at = ?, cancelled_by = ?
                       WHERE job_id = ? AND status = 'running' RETURNING job_id""",
                    (now, cancelled_by, job_id),
                ).fetchone()
                self._conn.commit()
                if updated is not None:
                    return {"job_id": job_id, "status": "running", "cancel_requested_at": now}
        raise RuntimeError(f"job status changed while requesting cancellation: {job_id}")

    def is_cancel_requested(self, job_id: str) -> bool:
        row = self._conn.execute(
            "SELECT cancel_requested_at FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row is not None and row["cancel_requested_at"] is not None

    def get_job(self, job_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return _job_dict(row)

    def get_queue_dashboard(self) -> dict:
        running_row = self._conn.execute(
            "SELECT * FROM jobs WHERE status = 'running' LIMIT 1"
        ).fetchone()
        running = _job_dict(running_row) if running_row else None

        queued_rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY enqueued_at"
        ).fetchall()
        queued = []
        for i, row in enumerate(queued_rows):
            d = _job_dict(row)
            d["position"] = i + 1
            queued.append(d)

        recent_rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status IN ('done', 'failed', 'cancelled') "
            "ORDER BY finished_at DESC LIMIT 10"
        ).fetchall()
        recent = [_job_dict(row) for row in recent_rows]

        return {"running": running, "queued": queued, "recent_completed": recent}

    def has_pending_jobs(self, workspace_id: str) -> bool:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM jobs WHERE workspace_id = ? AND status IN ('queued', 'running')",
            (workspace_id,),
        ).fetchone()
        return row["cnt"] > 0

    def recover_stale_jobs(self, workspace_resolver) -> list[str]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = 'running'"
        ).fetchall()
        recovered = []
        for row in rows:
            job = dict(row)
            run_id = job.get("run_id")
            ws_id = job["workspace_id"]
            ws_path = workspace_resolver(ws_id)
            if ws_path is None or run_id is None:
                self.update_status(job["job_id"], "failed", finished_at=_utcnow(),
                                   error="worker crashed during execution")
                recovered.append(job["job_id"])
                continue
            run_json = _resolve_run_json_path(ws_path, job, run_id)
            if run_json is None:
                self.update_status(
                    job["job_id"],
                    "failed",
                    finished_at=_utcnow(),
                    error="worker crashed with invalid run output directory",
                )
                recovered.append(job["job_id"])
                continue
            if run_json.exists():
                data = json.loads(run_json.read_text())
                if data.get("completed_at"):
                    if job.get("cancel_requested_at"):
                        self.update_status(job["job_id"], "cancelled", finished_at=_utcnow())
                    elif data.get("status") == "failed":
                        self.update_status(
                            job["job_id"],
                            "failed",
                            finished_at=_utcnow(),
                            error=data.get("failure_reason") or "run failed before worker recovery",
                        )
                    else:
                        self.update_status(job["job_id"], "done", finished_at=_utcnow())
                    recovered.append(job["job_id"])
                    continue
            self.update_status(job["job_id"], "failed", finished_at=_utcnow(),
                               error="worker crashed during execution")
            recovered.append(job["job_id"])
        return recovered

    def close(self) -> None:
        self._conn.close()


def _job_dict(row: sqlite3.Row) -> dict:
    """Decode the stored progress JSON for every public queue read path."""
    job = dict(row)
    if job["progress"] is not None:
        job["progress"] = json.loads(job["progress"])
    return job


def _resolve_run_json_path(workspace_path: Path, job: dict, run_id: str) -> Path | None:
    """Resolve a queued plan's canonical run path within its workspace."""
    try:
        plan = json.loads(job["plan_json"])
        output_dir = plan.get("output_dir", ".micro-eval/runs")
        workspace_root = workspace_path.resolve()
        run_json = (workspace_root / output_dir / run_id / "run.json").resolve()
        run_json.relative_to(workspace_root)
        return run_json
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


class QueueFullError(Exception):
    def __init__(self, current: int, maximum: int):
        self.current = current
        self.maximum = maximum
        super().__init__(f"queue full ({current}/{maximum})")
