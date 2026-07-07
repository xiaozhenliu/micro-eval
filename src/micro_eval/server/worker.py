"""Run worker — serial queue consumer for server mode."""

from __future__ import annotations

import asyncio
import atexit
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.run import RunPlan
from micro_eval.server.models import ServerConfig
from micro_eval.server.queue import QueueDB

logger = logging.getLogger(__name__)

PID_FILENAME = "worker.pid"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_content() -> str:
    """PID file payload: ``<pid> <boot-epoch>`` for identity verification."""
    import time
    return f"{os.getpid()} {time.monotonic_ns()}"


def _is_worker_alive(pid_path: Path) -> bool:
    """Check if the PID file references a live micro_eval worker.

    Returns True when we should refuse to start (another worker owns the lock).
    Returns False when the PID file is stale and can be replaced.
    """
    try:
        raw = pid_path.read_text().strip()
    except PermissionError:
        logger.error("Cannot read PID file (permission denied) — treating as occupied")
        return True
    except OSError:
        return False
    parts = raw.split()
    if not parts:
        return False
    try:
        old_pid = int(parts[0])
    except ValueError:
        logger.warning("Corrupt PID file, will replace: %s", pid_path)
        return False
    try:
        os.kill(old_pid, 0)
    except ProcessLookupError:
        logger.info("Removing stale PID file (PID %d no longer exists)", old_pid)
        return False
    except PermissionError:
        logger.error("PID %d exists but belongs to another user — treating as occupied", old_pid)
        return True
    except OSError:
        return False
    # PID exists and we can signal it. On macOS there's no /proc; use a
    # heuristic: if the PID file has a boot timestamp AND was written by the
    # current binary, the process is likely ours. Without /proc, fall back to
    # "alive = occupied" (safe: blocks startup rather than allowing parallel
    # workers, which is the worse failure mode).
    logger.error("Another worker appears to be running (PID %d)", old_pid)
    return True


def _write_pid(data_root: Path) -> None:
    import fcntl

    pid_path = data_root / PID_FILENAME
    lock_path = data_root / (PID_FILENAME + ".lock")

    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.error("Another worker is acquiring the PID lock")
            sys.exit(1)

        # Under the exclusive lock, safe to check→unlink→create without race.
        if pid_path.exists():
            if _is_worker_alive(pid_path):
                sys.exit(1)
            pid_path.unlink(missing_ok=True)

        fd = os.open(str(pid_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, _pid_content().encode())
        os.close(fd)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _clear_pid(data_root: Path) -> None:
    pid_path = data_root / PID_FILENAME
    if pid_path.exists():
        try:
            pid_path.unlink()
        except OSError:
            pass


async def worker_loop(
    data_root: Path,
    poll_interval: float = 2.0,
    run_timeout: int = 3600,
) -> None:
    db = QueueDB(data_root / "queue.db")

    from micro_eval.server.workspace import WorkspaceManager
    ws_manager = WorkspaceManager(data_root)

    def workspace_resolver(ws_id: str) -> Path | None:
        return ws_manager.resolve_path(ws_id)

    recovered = db.recover_stale_jobs(workspace_resolver)
    if recovered:
        logger.info("Recovered %d stale jobs: %s", len(recovered), recovered)

    shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    logger.info("Worker started, polling every %.1fs", poll_interval)

    while not shutdown.is_set():
        job = db.dequeue_next()
        if job is None:
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
            continue

        job_id = job["job_id"]
        ws_id = job["workspace_id"]
        ws_path = ws_manager.resolve_path(ws_id)
        if ws_path is None:
            db.update_status(job_id, "failed", finished_at=_utcnow(), error=f"workspace not found or invalid: {ws_id}")
            logger.error("Job %s failed: workspace %s not found or invalid", job_id, ws_id)
            continue
        logger.info("Executing job %s for workspace %s", job_id, ws_id)

        try:
            plan = RunPlan.model_validate_json(job["plan_json"])
            run_id = plan.run_id
            db.update_status(job_id, "running", run_id=run_id)

            def on_cell_complete(completed: int, total: int, result):
                db.update_progress(job_id, {
                    "completed_cells": completed,
                    "total_cells": total,
                    "current_task": result.task_id,
                    "current_config": result.configuration_id,
                })

            kernel = ExecutionKernel(project_root=ws_path, on_cell_complete=on_cell_complete)
            record = await asyncio.wait_for(
                kernel.run(plan),
                timeout=run_timeout,
            )

            if db.is_cancel_requested(job_id):
                db.update_status(job_id, "cancelled", finished_at=_utcnow())
                logger.info("Job %s cancelled (stop-after-run)", job_id)
            else:
                db.update_status(job_id, "done", finished_at=_utcnow())
                logger.info("Job %s completed successfully", job_id)

        except asyncio.TimeoutError:
            db.update_status(
                job_id, "failed", finished_at=_utcnow(),
                error=f"run timed out after {run_timeout}s",
            )
            logger.error("Job %s timed out", job_id)

        except Exception as exc:
            from micro_eval.engine.adapter import Redactor
            redacted_err = Redactor.from_env().redact(str(exc))
            db.update_status(job_id, "failed", finished_at=_utcnow(), error=redacted_err)
            logger.exception("Job %s failed: %s", job_id, exc)

    db.close()
    logger.info("Worker shut down gracefully")


def run_worker(data_root: Path, config: ServerConfig | None = None) -> None:
    if config is None:
        config = ServerConfig()
    _write_pid(data_root)
    atexit.register(_clear_pid, data_root)
    try:
        asyncio.run(worker_loop(
            data_root,
            poll_interval=config.worker_poll_interval_seconds,
            run_timeout=config.run_timeout_seconds,
        ))
    finally:
        _clear_pid(data_root)
