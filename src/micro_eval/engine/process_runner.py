"""Bounded argv-only process execution shared by workspace providers and agents."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micro_eval.engine.providers.base import CommandResult, ExecutionRequest


@dataclass
class _Capture:
    cap_bytes: int
    data: bytearray = field(default_factory=bytearray)
    truncated: bool = False

    async def drain(self, stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        try:
            while chunk := await stream.read(8192):
                remaining = max(0, self.cap_bytes - len(self.data))
                self.data.extend(chunk[:remaining])
                self.truncated |= len(chunk) > remaining
        except asyncio.CancelledError:
            self.truncated = True
            raise

    def text(self) -> str:
        encoded = self.data.decode(errors="replace").encode()
        self.truncated |= len(encoded) > self.cap_bytes
        return encoded[: self.cap_bytes].decode(errors="ignore")


async def read_limited(
    stream: asyncio.StreamReader | None, cap_bytes: int
) -> tuple[bytes, bool]:
    """Drain a pipe while retaining at most its byte budget."""
    capture = _Capture(max(0, cap_bytes))
    await capture.drain(stream)
    return bytes(capture.data), capture.truncated


async def run_process(request: ExecutionRequest) -> CommandResult:
    """Run a process session; deadlines include stdin and descendant-held pipes."""
    from micro_eval.engine.providers.base import CommandResult

    if (
        not request.argv
        or not isinstance(request.argv[0], str)
        or not request.argv[0]
        or any(not isinstance(arg, str) for arg in request.argv)
    ):
        raise ValueError("command argv must contain a nonempty executable and string arguments")
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        *request.argv,
        stdin=asyncio.subprocess.PIPE if request.stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=request.cwd,
        env=request.env,
        start_new_session=True,
    ))
    try:
        proc = await asyncio.shield(spawn)
    except asyncio.CancelledError:
        # Cancellation must not abandon a spawn that has already reached the OS
        # but has not returned its Process handle to this task yet.
        async def stop_spawn() -> None:
            try:
                spawned = await spawn
            except Exception:
                return
            communication, _, _ = _communicate(spawned, request)
            await _terminate(spawned, communication)

        await _finish_cleanup(asyncio.create_task(stop_spawn()))
        raise

    communication, stdout_capture, stderr_capture = _communicate(proc, request)
    timed_out = False
    try:
        done, _ = await asyncio.wait({communication}, timeout=request.timeout_s)
        if not done:
            timed_out = True
            await _terminate(proc, communication)
        else:
            await communication
            if _process_group_exists(proc.pid):
                # The leader can exit successfully after daemonizing a child
                # that closed its pipes. Stop owned writers before observation.
                await _terminate(proc, communication)
    except asyncio.CancelledError:
        await _finish_cleanup(asyncio.create_task(_terminate(proc, communication)))
        raise
    except BaseException:
        await _terminate(proc, communication)
        raise

    stdout, stderr = stdout_capture.text(), stderr_capture.text()
    return CommandResult(
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        stdout_truncated=stdout_capture.truncated,
        stderr_truncated=stderr_capture.truncated,
    )


def _communicate(
    proc: asyncio.subprocess.Process, request: ExecutionRequest
) -> tuple[asyncio.Task[None], _Capture, _Capture]:
    stdout_capture = _Capture(max(0, request.output_cap_bytes))
    stderr_capture = _Capture(max(0, request.output_cap_bytes))

    async def feed_stdin() -> None:
        if proc.stdin is None or request.stdin is None:
            return
        try:
            for offset in range(0, len(request.stdin), 65536):
                proc.stdin.write(request.stdin[offset : offset + 65536])
                await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.stdin.close()

    async def communicate() -> None:
        await asyncio.gather(
            feed_stdin(), proc.wait(),
            stdout_capture.drain(proc.stdout), stderr_capture.drain(proc.stderr),
        )

    return asyncio.create_task(communicate()), stdout_capture, stderr_capture


async def _finish_cleanup(cleanup: asyncio.Task[None]) -> None:
    """Keep process ownership through repeated external cancellation requests."""
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            continue
    await cleanup


async def _terminate(
    proc: asyncio.subprocess.Process, communication: asyncio.Task[None]
) -> None:
    """TERM, allow a grace period, KILL the session, and reap its leader."""
    _signal_process_group(proc, signal.SIGTERM)
    deadline = asyncio.get_running_loop().time() + 1.0
    await asyncio.wait({communication}, timeout=1.0)
    if _process_group_exists(proc.pid):
        await asyncio.sleep(max(0, deadline - asyncio.get_running_loop().time()))
        _signal_process_group(proc, signal.SIGKILL)
    done, _ = await asyncio.wait({communication}, timeout=1.0)
    if not done:
        # An escaped descendant can still own a copy of stdout/stderr. We cannot
        # kill a different session, but it must not retain this invocation. The
        # asyncio Process API exposes no public close for its read-pipe handles.
        communication.cancel()
        for reader in (proc.stdout, proc.stderr):
            if reader is not None:
                reader._transport.close()
        if proc.stdin is not None:
            transport = proc.stdin.transport
            if not transport.is_closing() or transport.get_write_buffer_size():
                transport.abort()
    await asyncio.gather(communication, return_exceptions=True)
    await proc.wait()


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # A denied probe is not evidence that the group disappeared. In
        # particular, macOS can report EPERM while an orphan is being reaped.
        return True
    return True


def _signal_process_group(proc: asyncio.subprocess.Process, sig: signal.Signals) -> None:
    """Signal all descendants, including when the session leader already exited."""
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        # A real signal denial must surface as failed cleanup, not success.
        raise
    except OSError:
        if proc.returncode is None:
            try:
                proc.send_signal(sig)
            except ProcessLookupError:
                pass
