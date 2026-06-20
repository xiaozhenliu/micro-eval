"""Agent bridges providing DeepEval model_callback implementations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from micro_eval.models.configuration import AgentSpec


class BridgeError(Exception):
    """Raised when agent bridge communication fails."""


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

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self.agent.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cwd),
            env=self.env,
        )

    async def send_turn(self, text: str) -> str:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise BridgeError("subprocess not started")
        self._turn_count += 1
        request = json.dumps({"turn": self._turn_count, "content": text}) + "\n"
        try:
            self._proc.stdin.write(request.encode())
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise BridgeError(f"subprocess stdin closed: {exc}") from exc
        try:
            raw = await asyncio.wait_for(
                self._proc.stdout.readline(), timeout=self.turn_timeout_s
            )
        except asyncio.TimeoutError:
            raise BridgeError(f"turn {self._turn_count} timed out after {self.turn_timeout_s}s")
        if not raw:
            raise BridgeError("subprocess stdout closed unexpectedly")
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BridgeError(f"invalid JSON from agent: {raw[:200]!r}") from exc
        return str(response.get("content", response.get("text", "")))

    async def stop(self) -> tuple[int | None, str]:
        if self._proc is None:
            return None, ""
        if self._proc.stdin and not self._proc.stdin.is_closing():
            self._proc.stdin.close()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=1)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        stderr = b""
        if self._proc.stderr:
            stderr = await self._proc.stderr.read()
        return self._proc.returncode, stderr.decode(errors="replace")

    @property
    def turn_count(self) -> int:
        return self._turn_count
