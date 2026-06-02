"""Agent execution engine with async parallel support."""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from micro_eval.models.schema import (
    AgentConfig,
    InputMode,
    OutputMode,
    Run,
    RunResult,
    Task,
    TaskStatus,
    EnvironmentSnapshot,
)


class RunnerError(Exception):
    """Raised when agent execution fails unexpectedly."""
    pass


class AgentRunner:
    """Executes agents against tasks with isolation and timeout."""

    SUMMARY_LIMIT = 500
    MAX_OUTPUT_BYTES = 10 * 1024 * 1024
    INTERNAL_ARTIFACT_NAMES = {"input.txt", "stdout.txt", "stderr.txt"}

    def __init__(self, work_dir: Optional[Path] = None):
        self.work_dir = work_dir or Path.cwd()

    async def run_eval(
        self,
        baseline: AgentConfig,
        candidate: AgentConfig,
        tasks: list[Task],
        parallel: bool = True,
    ) -> Run:
        """Run evaluation across all tasks for both agents."""
        run_id = self._new_run_id()
        ts = datetime.now(timezone.utc).isoformat()

        results: list[RunResult] = []

        if parallel:
            coros = []
            for task in tasks:
                coros.append(
                    self._run_single(
                        baseline, task, run_id=run_id, invocation_role="baseline"
                    )
                )
                coros.append(
                    self._run_single(
                        candidate, task, run_id=run_id, invocation_role="candidate"
                    )
                )
            results = await asyncio.gather(*coros)
        else:
            for task in tasks:
                r1 = await self._run_single(
                    baseline, task, run_id=run_id, invocation_role="baseline"
                )
                r2 = await self._run_single(
                    candidate, task, run_id=run_id, invocation_role="candidate"
                )
                results.extend([r1, r2])

        import platform
        env_snapshot = EnvironmentSnapshot(
            python_version=platform.python_version(),
            timestamp=ts,
        )

        return Run(
            id=run_id,
            schema_version="1.0",
            timestamp=ts,
            baseline_agent=baseline.name,
            candidate_agent=candidate.name,
            tasks=[t.id for t in tasks],
            results=list(results),
            environment=env_snapshot,
            execution_order="parallel" if parallel else "sequential",
        )

    async def _run_single(
        self,
        agent: AgentConfig,
        task: Task,
        run_id: str = "manual",
        invocation_role: Optional[str] = None,
    ) -> RunResult:
        """Execute a single agent on a single task."""
        start = time.monotonic()
        output_dir = self._cell_output_dir(
            run_id, task, agent, invocation_role=invocation_role
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "output.txt"
        input_file: Optional[Path] = None

        try:
            # Prepare input
            stdin_data: Optional[str] = None
            if agent.input_mode == InputMode.file:
                input_file = output_dir / "input.txt"
                input_file.write_text(task.input_payload)
            else:
                stdin_data = task.input_payload

            argv = self._build_argv(
                agent.command,
                output_dir=output_dir,
                output_file=output_file,
                input_file=input_file,
            )
            env = self._build_env(agent, output_dir, output_file)

            # Execute
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=(
                    asyncio.subprocess.PIPE
                    if stdin_data is not None
                    else None
                ),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.work_dir),
                env=env,
            )

            stdout_task = asyncio.create_task(
                self._read_limited(proc.stdout)
            )
            stderr_task = asyncio.create_task(
                self._read_limited(proc.stderr)
            )

            if stdin_data is not None and proc.stdin:
                try:
                    proc.stdin.write(stdin_data.encode())
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    proc.stdin.close()

            timed_out = False
            try:
                await asyncio.wait_for(proc.wait(), timeout=agent.timeout_s)
            except asyncio.TimeoutError:
                timed_out = True
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            stdout_bytes, stdout_truncated = await stdout_task
            stderr_bytes, stderr_truncated = await stderr_task

            latency = time.monotonic() - start
            stdout_text = self._redact(
                stdout_bytes.decode(errors="replace"), agent
            )
            stderr_text = self._redact(
                stderr_bytes.decode(errors="replace"), agent
            )
            stdout_ref = self._write_text_artifact(
                output_dir / "stdout.txt", stdout_text
            )
            stderr_ref = self._write_text_artifact(
                output_dir / "stderr.txt", stderr_text
            )

            output_artifacts = self._collect_output_artifacts(
                output_dir, agent
            )
            output = self._select_output(agent, output_file, stdout_text)
            output_summary = self._summary(output)
            stdout_summary = self._summary(stdout_text)
            stderr_summary = self._summary(stderr_text)

            if timed_out:
                latency = time.monotonic() - start
                return RunResult(
                    task_id=task.id,
                    agent_name=agent.name,
                    status=TaskStatus.timeout,
                    output_summary=output_summary,
                    stdout_summary=stdout_summary,
                    stderr_summary=stderr_summary,
                    stdout_ref=stdout_ref,
                    stderr_ref=stderr_ref,
                    exit_code=proc.returncode,
                    output_dir=self._path_ref(output_dir),
                    output_artifacts=output_artifacts,
                    latency_s=latency,
                    failure_mode="timeout",
                )

            if stdout_truncated or stderr_truncated:
                stderr_summary = self._summary(
                    f"{stderr_text}\n[micro-eval] output truncated"
                )

            if proc.returncode != 0:
                return RunResult(
                    task_id=task.id,
                    agent_name=agent.name,
                    status=TaskStatus.error,
                    output_summary=output_summary,
                    stdout_summary=stdout_summary,
                    stderr_summary=stderr_summary,
                    stdout_ref=stdout_ref,
                    stderr_ref=stderr_ref,
                    exit_code=proc.returncode,
                    output_dir=self._path_ref(output_dir),
                    output_artifacts=output_artifacts,
                    latency_s=latency,
                    failure_mode=f"exit_code_{proc.returncode}",
                )

            return RunResult(
                task_id=task.id,
                agent_name=agent.name,
                status=TaskStatus.passed,
                output_summary=output_summary,
                stdout_summary=stdout_summary,
                stderr_summary=stderr_summary,
                stdout_ref=stdout_ref,
                stderr_ref=stderr_ref,
                exit_code=proc.returncode,
                output_dir=self._path_ref(output_dir),
                output_artifacts=output_artifacts,
                latency_s=latency,
            )

        except Exception as e:
            latency = time.monotonic() - start
            return RunResult(
                task_id=task.id,
                agent_name=agent.name,
                status=TaskStatus.error,
                output_summary="",
                output_dir=self._path_ref(output_dir),
                latency_s=latency,
                failure_mode=str(e),
            )

    def _build_argv(
        self,
        command: str,
        output_dir: Path,
        output_file: Path,
        input_file: Optional[Path],
    ) -> list[str]:
        """Build a subprocess argv without shell interpolation."""
        try:
            argv = shlex.split(command)
        except ValueError as e:
            raise RunnerError(f"Invalid agent command: {e}") from e
        if not argv:
            raise RunnerError("Agent command cannot be empty")

        replacements = {
            "{output_dir}": str(output_dir),
            "{output_file}": str(output_file),
            "{input_file}": str(input_file) if input_file else "",
        }
        for i, arg in enumerate(argv):
            for placeholder, value in replacements.items():
                arg = arg.replace(placeholder, value)
            argv[i] = arg
        return argv

    def _build_env(
        self, agent: AgentConfig, output_dir: Path, output_file: Path
    ) -> dict[str, str]:
        """Build an allowlisted environment for agent invocation."""
        inherited_keys = (
            "PATH",
            "HOME",
            "TMPDIR",
            "TEMP",
            "TMP",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key in inherited_keys
        }
        env.update(agent.env)
        env["MICRO_EVAL_OUTPUT_DIR"] = str(output_dir)
        env["MICRO_EVAL_OUTPUT_FILE"] = str(output_file)
        return env

    def _new_run_id(self) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"run-{timestamp}-{secrets.token_hex(4)}"

    def _cell_output_dir(
        self,
        run_id: str,
        task: Task,
        agent: AgentConfig,
        invocation_role: Optional[str] = None,
    ) -> Path:
        segments = [self._safe_path_segment(task.id)]
        if invocation_role:
            segments.append(self._safe_path_segment(invocation_role))
        segments.append(self._safe_path_segment(agent.name))
        cell_id = "--".join(segments)
        return self.work_dir / ".micro-eval" / "artifacts" / run_id / cell_id

    def _safe_path_segment(self, value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
        return safe or "unknown"

    async def _read_limited(
        self, stream: Optional[asyncio.StreamReader]
    ) -> tuple[bytes, bool]:
        """Read a subprocess stream while capping retained bytes."""
        if stream is None:
            return b"", False

        chunks: list[bytes] = []
        retained = 0
        truncated = False
        while True:
            chunk = await stream.read(8192)
            if not chunk:
                break
            remaining = self.MAX_OUTPUT_BYTES - retained
            if remaining > 0:
                chunks.append(chunk[:remaining])
                retained += min(len(chunk), remaining)
            if len(chunk) > remaining:
                truncated = True
        return b"".join(chunks), truncated

    def _redact(self, text: str, agent: AgentConfig) -> str:
        redacted = text
        for value in agent.env.values():
            if value and len(value) >= 4:
                redacted = redacted.replace(value, "[REDACTED]")
        return redacted

    def _write_text_artifact(self, path: Path, text: str) -> str:
        path.write_text(text)
        return self._path_ref(path)

    def _collect_output_artifacts(
        self, output_dir: Path, agent: AgentConfig
    ) -> list[str]:
        artifacts: list[str] = []
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file() or path.name in self.INTERNAL_ARTIFACT_NAMES:
                continue
            self._redact_text_file_in_place(path, agent)
            artifacts.append(self._path_ref(path))
        return artifacts

    def _select_output(
        self, agent: AgentConfig, output_file: Path, stdout_text: str
    ) -> str:
        if agent.output_mode == OutputMode.stdout:
            return stdout_text

        if agent.output_mode == OutputMode.file:
            if output_file.exists():
                return self._redact_file(output_file, agent)
            candidates = [
                path
                for path in sorted(output_file.parent.iterdir())
                if path.is_file()
                and path.name not in self.INTERNAL_ARTIFACT_NAMES
            ]
            if candidates:
                return self._redact_file(candidates[0], agent)
            return ""

        if agent.output_mode == OutputMode.directory:
            artifacts = self._collect_output_artifacts(
                output_file.parent, agent
            )
            if stdout_text:
                return stdout_text
            return "\n".join(artifacts)

        return stdout_text

    def _redact_file(self, path: Path, agent: AgentConfig) -> str:
        try:
            return self._redact(path.read_text(errors="replace"), agent)
        except OSError as e:
            raise RunnerError(f"Unable to read output artifact {path}: {e}") from e

    def _redact_text_file_in_place(
        self, path: Path, agent: AgentConfig
    ) -> None:
        data = path.read_bytes()
        if b"\0" in data:
            return
        text = data.decode(errors="replace")
        redacted = self._redact(text, agent)
        if redacted != text:
            path.write_text(redacted)

    def _summary(self, text: str) -> str:
        return text[: self.SUMMARY_LIMIT]

    def _path_ref(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.work_dir))
        except ValueError:
            return str(path)
