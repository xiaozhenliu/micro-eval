"""Process ownership includes deadlines, stdin, descendants, and cancellation."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from micro_eval.engine.process_runner import run_process
from micro_eval.engine.providers.base import ExecutionRequest


async def _wait_pid_file(path: Path) -> int:
    async with asyncio.timeout(5):
        while not path.exists():
            await asyncio.sleep(0.01)
    return int(path.read_text())


def _running(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists() and stat_path.read_text().split(") ", 1)[1].startswith("Z"):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _assert_stopped(pid: int) -> None:
    try:
        async with asyncio.timeout(3):
            while _running(pid):
                await asyncio.sleep(0.02)
    finally:
        if _running(pid):
            os.kill(pid, signal.SIGKILL)


async def test_timeout_covers_stdin_backpressure(tmp_path: Path) -> None:
    result = await asyncio.wait_for(
        run_process(ExecutionRequest(
            argv=[sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=b"x" * (4 * 1024 * 1024),
            timeout_s=0.1,
            cwd=tmp_path,
        )),
        timeout=5,
    )
    assert result.timed_out
    assert result.exit_code < 0


async def test_exit_of_leader_does_not_disable_pipe_timeout(tmp_path: Path) -> None:
    code = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)']); "
        "pathlib.Path('child.pid').write_text(str(child.pid))"
    )
    result = await asyncio.wait_for(
        run_process(ExecutionRequest(
            argv=[sys.executable, "-c", code], cwd=tmp_path, timeout_s=0.4,
        )),
        timeout=5,
    )
    assert result.timed_out
    await _assert_stopped(int((tmp_path / "child.pid").read_text()))


async def test_cancellation_terminates_and_reaps_the_owned_session(tmp_path: Path) -> None:
    code = (
        "import os, pathlib, signal, subprocess, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "pathlib.Path('leader.pid').write_text(str(os.getpid())); "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)']); "
        "pathlib.Path('child.pid').write_text(str(child.pid)); time.sleep(30)"
    )
    task = asyncio.create_task(run_process(ExecutionRequest(
        argv=[sys.executable, "-c", code], cwd=tmp_path,
    )))
    child = await _wait_pid_file(tmp_path / "child.pid")
    leader = await _wait_pid_file(tmp_path / "leader.pid")
    task.cancel()
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    await _assert_stopped(leader)
    await _assert_stopped(child)


async def test_streams_are_independently_bounded_and_argv_is_literal() -> None:
    result = await run_process(ExecutionRequest(
        argv=[sys.executable, "-c", "import sys; print(sys.argv[1], end=''); sys.stderr.write('e'*100)", "$(false); literal"],
        output_cap_bytes=8,
    ))
    assert result.stdout == "$(false)"
    assert result.stderr == "e" * 8
    assert result.stdout_truncated and result.stderr_truncated
    assert result.exit_code == 0


@pytest.mark.parametrize("stdin", [None, b"input"])
async def test_escaped_pipe_holder_cannot_block_timeout_completion(
    tmp_path: Path, stdin: bytes | None,
) -> None:
    code = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True); "
        "pathlib.Path('escaped.pid').write_text(str(child.pid)); "
        "print('partial', flush=True); time.sleep(30)"
    )
    try:
        result = await asyncio.wait_for(run_process(ExecutionRequest(
            argv=[sys.executable, "-c", code], cwd=tmp_path, timeout_s=0.3, stdin=stdin,
        )), timeout=5)
        assert result.timed_out
        assert result.stdout == "partial\n"
        assert result.stdout_truncated
    finally:
        pid_file = tmp_path / "escaped.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text())
            if _running(pid):
                os.kill(pid, signal.SIGKILL)


async def test_cancellation_during_spawn_keeps_process_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawned = asyncio.Event()
    release = asyncio.Event()
    processes: list[asyncio.subprocess.Process] = []
    original = asyncio.create_subprocess_exec

    async def delayed_spawn(*args, **kwargs):
        proc = await original(*args, **kwargs)
        processes.append(proc)
        spawned.set()
        await release.wait()
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    task = asyncio.create_task(run_process(ExecutionRequest(
        argv=[sys.executable, "-c", "import time; time.sleep(30)"],
    )))
    await asyncio.wait_for(spawned.wait(), timeout=3)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    assert processes[0].returncode is not None
    await _assert_stopped(processes[0].pid)


async def test_decoding_invalid_bytes_preserves_stream_byte_cap() -> None:
    result = await run_process(ExecutionRequest(
        argv=[sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff' * 10)"],
        output_cap_bytes=10,
    ))
    assert len(result.stdout.encode()) <= 10
    assert result.stdout_truncated


async def test_successful_leader_does_not_leave_detached_pipe_child(tmp_path: Path) -> None:
    code = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "pathlib.Path('child.pid').write_text(str(child.pid))"
    )
    result = await asyncio.wait_for(run_process(ExecutionRequest(
        argv=[sys.executable, "-c", code], cwd=tmp_path,
    )), timeout=5)
    assert result.exit_code == 0
    assert not result.timed_out
    await _assert_stopped(int((tmp_path / "child.pid").read_text()))
