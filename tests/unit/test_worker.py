"""Unit tests for the run worker PID file handling (GRO-178 / M6)."""

from __future__ import annotations

import os

import pytest

from micro_eval.server.worker import PID_FILENAME, _write_pid, _is_worker_alive


def _read_pid(tmp_path) -> int:
    raw = (tmp_path / PID_FILENAME).read_text().strip()
    return int(raw.split()[0])


def test_fresh_start_creates_pid_atomically(tmp_path):
    _write_pid(tmp_path)
    assert _read_pid(tmp_path) == os.getpid()


def test_stale_pid_takeover(tmp_path):
    """Worker should take over when pid file points to a non-existent process."""
    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("999999999 0")
    _write_pid(tmp_path)
    assert _read_pid(tmp_path) == os.getpid()


def test_corrupt_pid_file_replaced(tmp_path):
    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("not-a-number")
    _write_pid(tmp_path)
    assert _read_pid(tmp_path) == os.getpid()


def test_own_pid_alive_blocks_startup(tmp_path):
    """If the PID file points to a live process (self in this case), exit."""
    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text(f"{os.getpid()} 12345")
    with pytest.raises(SystemExit):
        _write_pid(tmp_path)


def test_is_worker_alive_nonexistent_pid(tmp_path):
    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("999999999 0")
    assert _is_worker_alive(pid_path) is False


def test_is_worker_alive_self(tmp_path):
    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text(f"{os.getpid()} 0")
    assert _is_worker_alive(pid_path) is True


def test_is_worker_alive_missing_file(tmp_path):
    pid_path = tmp_path / PID_FILENAME
    assert _is_worker_alive(pid_path) is False


def test_is_worker_alive_empty_file(tmp_path):
    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("")
    assert _is_worker_alive(pid_path) is False


def test_eperm_pid_treated_as_occupied(tmp_path, monkeypatch):
    """EPERM (process belongs to another user) must be treated as occupied."""
    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("1 0")

    def fake_kill(pid, sig):
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(os, "kill", fake_kill)
    assert _is_worker_alive(pid_path) is True


def test_flock_serialises_stale_cleanup(tmp_path):
    """Flock ensures only one worker can clean up a stale PID at a time."""
    import fcntl

    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("999999999 0")
    lock_path = tmp_path / (PID_FILENAME + ".lock")
    # Pre-acquire the flock so _write_pid fails immediately.
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o644)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(SystemExit):
            _write_pid(tmp_path)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def test_file_read_permission_denied_treated_as_occupied(tmp_path):
    """If we can't read the PID file due to permissions, treat as occupied."""
    import unittest.mock

    pid_path = tmp_path / PID_FILENAME
    pid_path.write_text("12345 0")

    with unittest.mock.patch.object(type(pid_path), "read_text", side_effect=PermissionError("denied")):
        assert _is_worker_alive(pid_path) is True
