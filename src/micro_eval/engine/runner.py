"""Agent execution engine with async parallel support."""

from __future__ import annotations

import asyncio
import tempfile
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
        run_id = f"run-{int(time.time())}"
        ts = datetime.now(timezone.utc).isoformat()

        results: list[RunResult] = []

        if parallel:
            coros = []
            for task in tasks:
                coros.append(self._run_single(baseline, task))
                coros.append(self._run_single(candidate, task))
            results = await asyncio.gather(*coros)
        else:
            for task in tasks:
                r1 = await self._run_single(baseline, task)
                r2 = await self._run_single(candidate, task)
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
        self, agent: AgentConfig, task: Task
    ) -> RunResult:
        """Execute a single agent on a single task."""
        start = time.monotonic()
        output_dir = Path(tempfile.mkdtemp(prefix="micro-eval-out-"))
        input_file: Optional[Path] = None

        try:
            # Prepare command with template vars
            cmd = agent.command.replace("{output_dir}", str(output_dir))

            # Prepare input
            stdin_data: Optional[str] = None
            if agent.input_mode == InputMode.file:
                input_file = output_dir / "input.txt"
                input_file.write_text(task.input_payload)
                cmd = cmd.replace("{input_file}", str(input_file))
            else:
                stdin_data = task.input_payload

            # Build environment (merge with current env, not replace)
            import os
            env = os.environ.copy()
            if agent.env:
                env.update(agent.env)

            # Execute
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.work_dir),
                env=env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(
                        input=stdin_data.encode() if stdin_data else None
                    ),
                    timeout=agent.timeout_s,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                latency = time.monotonic() - start
                return RunResult(
                    task_id=task.id,
                    agent_name=agent.name,
                    status=TaskStatus.timeout,
                    output_summary="",
                    latency_s=latency,
                    failure_mode="timeout",
                )

            latency = time.monotonic() - start
            stdout_text = stdout_bytes.decode(errors="replace")

            # Collect output based on mode
            if agent.output_mode == OutputMode.stdout:
                output = stdout_text
            elif agent.output_mode == OutputMode.file:
                out_files = list(output_dir.iterdir())
                if out_files:
                    output = out_files[0].read_text(errors="replace")
                else:
                    output = ""
            else:
                output = stdout_text

            if proc.returncode != 0:
                return RunResult(
                    task_id=task.id,
                    agent_name=agent.name,
                    status=TaskStatus.error,
                    output_summary=output[:500],
                    latency_s=latency,
                    failure_mode=f"exit_code_{proc.returncode}",
                )

            return RunResult(
                task_id=task.id,
                agent_name=agent.name,
                status=TaskStatus.passed,
                output_summary=output[:500],
                latency_s=latency,
            )

        except Exception as e:
            latency = time.monotonic() - start
            return RunResult(
                task_id=task.id,
                agent_name=agent.name,
                status=TaskStatus.error,
                output_summary="",
                latency_s=latency,
                failure_mode=str(e),
            )
