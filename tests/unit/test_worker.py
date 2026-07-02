"""Unit tests for the run worker PID file handling."""

from __future__ import annotations

import os


def test_stale_pid_takeover(tmp_path):
    """Worker should take over when pid file points to a non-existent process."""
    from micro_eval.server.worker import PID_FILENAME, _write_pid

    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("999999999")  # non-existent PID
    _write_pid(tmp_path)
    assert pid_path.read_text().strip() == str(os.getpid())
