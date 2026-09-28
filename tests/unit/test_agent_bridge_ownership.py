"""Conversation subprocess ownership survives deadlines and cancellation."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from micro_eval.engine.agent_bridge import BridgeError, SubprocessBridge
from micro_eval.models.configuration import AgentSpec


@pytest.fixture(autouse=True)
def short_graceful_wait(monkeypatch) -> None:
    monkeypatch.setattr("micro_eval.engine.agent_bridge.GRACEFUL_STOP_TIMEOUT_S", 0.05)


def _bridge(tmp_path: Path, script: str, *, timeout: float = 0.2) -> SubprocessBridge:
    return SubprocessBridge(
        agent=AgentSpec(name="ownership", command=[sys.executable, "-c", script]),
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        turn_timeout_s=timeout,
    )


async def _pid(path: Path) -> int:
    async with asyncio.timeout(3):
        while not path.exists():
            await asyncio.sleep(0.01)
    return int(path.read_text())


def _running(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists() and stat.read_text().split(") ", 1)[1].startswith("Z"):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _stopped(pid: int) -> None:
    try:
        async with asyncio.timeout(3):
            while _running(pid):
                await asyncio.sleep(0.02)
    finally:
        if _running(pid):
            os.kill(pid, signal.SIGKILL)


@pytest.mark.parametrize("inherit_pipes", [True, False])
async def test_successful_leader_does_not_leave_descendants(tmp_path: Path, inherit_pipes: bool) -> None:
    streams = "" if inherit_pipes else ", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL"
    bridge = _bridge(tmp_path, (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)']"
        f"{streams}); pathlib.Path('child.pid').write_text(str(child.pid))"
    ))
    await bridge.start()
    child = await _pid(tmp_path / "child.pid")
    try:
        async with asyncio.timeout(3):
            while bridge._proc is not None and bridge._proc.returncode is None:
                await asyncio.sleep(0.01)
        code, _ = await asyncio.wait_for(bridge.stop(), timeout=4)
        assert code == 0
        await _stopped(child)
    finally:
        if _running(child):
            os.kill(child, signal.SIGKILL)


async def test_repeated_cancellation_of_stop_finishes_group_cleanup(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, (
        "import pathlib, signal, subprocess, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)']); "
        "pathlib.Path('child.pid').write_text(str(child.pid)); time.sleep(30)"
    ))
    await bridge.start()
    child = await _pid(tmp_path / "child.pid")
    stopping = asyncio.create_task(bridge.stop())
    await asyncio.sleep(0.02)
    stopping.cancel()
    await asyncio.sleep(0.02)
    stopping.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(stopping, timeout=4)

    assert bridge._proc is not None and bridge._proc.returncode is not None
    await _stopped(bridge._proc.pid)
    await _stopped(child)
    assert (await bridge.stop())[0] == bridge._proc.returncode


async def test_cancellation_during_spawn_retains_process_handle(tmp_path: Path, monkeypatch) -> None:
    created = asyncio.Event()
    release = asyncio.Event()
    processes: list[asyncio.subprocess.Process] = []
    original = asyncio.create_subprocess_exec

    async def delayed_spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        created.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    bridge = _bridge(tmp_path, "import time; time.sleep(30)")
    starting = asyncio.create_task(bridge.start())
    await asyncio.wait_for(created.wait(), timeout=3)
    starting.cancel()
    await asyncio.sleep(0)
    starting.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(starting, timeout=4)

    assert processes[0].returncode is not None
    await _stopped(processes[0].pid)


async def test_turn_deadline_includes_blocked_stdin(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, "import time; time.sleep(30)", timeout=0.1)
    await bridge.start()
    try:
        with pytest.raises(BridgeError, match="timed out") as error:
            await asyncio.wait_for(bridge.send_turn("x" * (4 * 1024 * 1024)), timeout=2)
        assert error.value.timed_out
    finally:
        await asyncio.wait_for(bridge.stop(), timeout=4)


@pytest.mark.parametrize("oversized", [True, False])
async def test_invalid_response_never_appears_in_bridge_errors(tmp_path: Path, oversized: bool) -> None:
    secret = "private-agent-response"
    count = 128 * 1024 if oversized else 1
    bridge = _bridge(tmp_path, f"import sys; sys.stdin.readline(); print({secret!r} + 'x' * {count}, flush=True)", timeout=2)
    await bridge.start()
    try:
        with pytest.raises(BridgeError) as error:
            await bridge.send_turn("hello")
        assert secret not in str(error.value)
        assert "line limit" in str(error.value) if oversized else "invalid JSON" in str(error.value)
    finally:
        await asyncio.wait_for(bridge.stop(), timeout=4)


async def test_escaped_pipe_holder_does_not_block_bridge_stop(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True); "
        "pathlib.Path('escaped.pid').write_text(str(child.pid)); time.sleep(30)"
    ))
    await bridge.start()
    child = await _pid(tmp_path / "escaped.pid")
    try:
        code, _ = await asyncio.wait_for(bridge.stop(), timeout=4)
        assert code is not None
        assert _running(child), "a different session is outside logical process-group ownership"
    finally:
        if _running(child):
            os.kill(child, signal.SIGKILL)
