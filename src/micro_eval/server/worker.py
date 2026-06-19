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


def _write_pid(data_root: Path) -> None:
    pid_path = data_root / PID_FILENAME
    if pid_path.exists():
        old_pid = int(pid_path.read_text().strip())
        try:
            os.kill(old_pid, 0)
            logger.error("Another worker is already running (PID: %d)", old_pid)
            sys.exit(1)
        except OSError:
            pass
    pid_path.write_text(str(os.getpid()))


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

    def workspace_resolver(ws_id: str) -> Path | None:
        ws_path = data_root / "workspaces" / ws_id
        if ws_path.exists():
            return ws_path
        return None

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
        ws_path = data_root / "workspaces" / ws_id
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
            db.update_status(job_id, "failed", finished_at=_utcnow(), error=str(exc))
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
