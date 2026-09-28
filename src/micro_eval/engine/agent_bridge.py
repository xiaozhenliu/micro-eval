"""Agent bridges providing DeepEval model_callback implementations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from micro_eval.engine.process_runner import (
    _finish_cleanup,
    _process_group_exists,
    _terminate,
    read_limited,
)
from micro_eval.models.configuration import AgentSpec

STDERR_CAP_BYTES = 10 * 1024 * 1024
GRACEFUL_STOP_TIMEOUT_S = 5.0


class BridgeError(Exception):
    """Raised when agent bridge communication fails."""

    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.timed_out = timed_out


class SubprocessBridge:
    """Bridge a subprocess agent to DeepEval's model_callback via JSONL on stdin/stdout.

    The subprocess stays alive for the duration of the conversation.
    Each turn: write a JSON line to stdin, read a JSON line from stdout.
    """

    def __init__(
        self,
        *,
        agent: AgentSpec,
        cwd: Path,
        env: dict[str, str],
        turn_timeout_s: float = 60.0,
    ):
        self.agent = agent
        self.cwd = cwd
        self.env = env
        self.turn_timeout_s = turn_timeout_s
        self._proc: asyncio.subprocess.Process | None = None
        self._turn_count = 0
        self._stderr_buf = bytearray()
        self._stderr_task: asyncio.Task | None = None
        self._stop_task: asyncio.Task[tuple[int | None, str]] | None = None
        self._pending_turns: set[asyncio.Task[bytes]] = set()
        self._stopping = False

    async def _drain_stderr(self) -> None:
        """Background task: consume stderr to prevent OS pipe buffer from blocking the agent."""
        assert self._proc is not None and self._proc.stderr is not None
        try:
            while True:
                chunk = await self._proc.stderr.read(8192)
                if not chunk:
                    break
                remaining = STDERR_CAP_BYTES - len(self._stderr_buf)
                if remaining > 0:
                    self._stderr_buf.extend(chunk[:remaining])
        except Exception:
            pass

    async def start(self) -> None:
        if self._proc is not None:
            raise BridgeError("subprocess already started")
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            *self.agent.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cwd),
            env=self.env,
            start_new_session=True,
        ))
        try:
            self._proc = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            async def stop_spawn() -> None:
                try:
                    self._proc = await spawn
                except Exception:
                    return
                self._stderr_task = asyncio.create_task(self._drain_stderr())
                await self.stop()

            await _finish_cleanup(asyncio.create_task(stop_spawn()))
            raise
        except OSError as exc:
            raise BridgeError("subprocess could not be started") from exc
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def send_turn(self, text: str) -> str:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise BridgeError("subprocess not started")
        if self._stopping:
            raise BridgeError("subprocess is stopping")
        self._turn_count += 1
        request = (json.dumps({"turn": self._turn_count, "content": text}) + "\n").encode()

        async def exchange() -> bytes:
            assert self._proc is not None and self._proc.stdin is not None and self._proc.stdout is not None
            for offset in range(0, len(request), 65536):
                self._proc.stdin.write(request[offset : offset + 65536])
                await self._proc.stdin.drain()
            return await self._proc.stdout.readline()

        pending = asyncio.create_task(exchange())
        self._pending_turns.add(pending)
        try:
            raw = await asyncio.wait_for(pending, timeout=self.turn_timeout_s)
        except asyncio.TimeoutError:
            raise BridgeError(
                f"turn {self._turn_count} timed out after {self.turn_timeout_s}s", timed_out=True
            ) from None
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise BridgeError("subprocess stdin closed") from exc
        except ValueError as exc:
            raise BridgeError("agent response exceeded the line limit") from exc
        finally:
            self._pending_turns.discard(pending)
        if not raw:
            raise BridgeError("subprocess stdout closed unexpectedly")
        try:
            response = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BridgeError("invalid JSON from agent") from exc
        if not isinstance(response, dict):
            raise BridgeError("agent response must be a JSON object")
        return str(response.get("content", response.get("text", "")))

    async def stop(self) -> tuple[int | None, str]:
        if self._proc is None:
            return None, ""
        if self._stop_task is None:
            self._stopping = True
            self._stop_task = asyncio.create_task(self._stop_process())
        try:
            return await asyncio.shield(self._stop_task)
        except asyncio.CancelledError:
            await _finish_cleanup(self._stop_task)
            raise

    async def _stop_process(self) -> tuple[int | None, str]:
        assert self._proc is not None
        pending = list(self._pending_turns)
        for turn in pending:
            turn.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if self._proc.stdin and not self._proc.stdin.is_closing():
            self._proc.stdin.close()

        async def drain() -> None:
            assert self._proc is not None
            await asyncio.gather(
                self._proc.wait(),
                read_limited(self._proc.stdout, 0),
                self._stderr_task if self._stderr_task is not None else asyncio.sleep(0),
            )

        communication = asyncio.create_task(drain())
        done, _ = await asyncio.wait({communication}, timeout=GRACEFUL_STOP_TIMEOUT_S)
        if not done or _process_group_exists(self._proc.pid):
            # Shared termination also bounds pipes held by descendants that
            # left the session; logical isolation cannot kill those sessions.
            await _terminate(self._proc, communication)
        else:
            await communication
        return self._proc.returncode, bytes(self._stderr_buf).decode(errors="replace")

    @property
    def turn_count(self) -> int:
        return self._turn_count
