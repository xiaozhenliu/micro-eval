"""Safe argv-based agent adapter."""

from __future__ import annotations

import asyncio
import logging
import os
import stat
import sys
import time
from pathlib import Path

from micro_eval.models.configuration import AgentSpec, InputMode, OutputMode
from micro_eval.models.ids import looks_binary
from micro_eval.models.run import AdapterResult, CellStatus


class AdapterError(Exception):
    """Raised when adapter setup fails before process execution."""


_logger = logging.getLogger(__name__)

_MIN_SECRET_LENGTH = 4


class Redactor:
    """Named text redactor for declared environment values."""

    SECRET_ENV_PREFIX = "MICRO_EVAL_SECRET_"

    def __init__(self, values: dict[str, str]):
        self.values: dict[str, str] = {}
        for name, value in values.items():
            if not value:
                continue
            if len(value) < _MIN_SECRET_LENGTH:
                _logger.warning(
                    "secret %s is shorter than %d chars; skipping redaction to avoid over-replacement",
                    name,
                    _MIN_SECRET_LENGTH,
                )
                continue
            self.values[name] = value

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Redactor":
        """Build a redactor from declared MICRO_EVAL_SECRET_* environment values."""
        source = env if env is not None else dict(os.environ)
        values = {key: value for key, value in source.items() if key.startswith(cls.SECRET_ENV_PREFIX)}
        return cls(values)

    def redact(self, text: str) -> str:
        redacted = text
        for name, value in self.values.items():
            redacted = redacted.replace(value, f"[REDACTED:{name}]")
        return redacted


class AgentAdapter:
    """Invoke agents through asyncio.create_subprocess_exec."""

    inherited_env_keys = {
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
    }

    def __init__(self, *, output_cap_bytes: int = 10 * 1024 * 1024):
        self.output_cap_bytes = output_cap_bytes

    async def invoke(
        self,
        *,
        agent: AgentSpec,
        input_payload: str,
        cwd: Path,
        output_dir: Path,
        trace_id: str = "",
    ) -> tuple[AdapterResult, Redactor]:
        """Run one agent invocation and return normalized facts."""
        output_dir.mkdir(parents=True, exist_ok=True)
        input_file = output_dir / "input.txt"
        output_file = output_dir / "output.txt"

        stdin_data: str | None = input_payload
        if agent.input_mode == InputMode.file:
            input_file.write_text(input_payload)
            stdin_data = None

        env, redactor = self._build_env(agent, output_dir, output_file, trace_id)
        argv = self._build_argv(agent, output_dir, output_file, input_file)
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env=env,
            )
            stdout_task = asyncio.create_task(self._read_limited(proc.stdout))
            stderr_task = asyncio.create_task(self._read_limited(proc.stderr))
            if stdin_data is not None and proc.stdin is not None:
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
            stdout = redactor.redact(stdout_bytes.decode(errors="replace"))
            stderr = redactor.redact(stderr_bytes.decode(errors="replace"))
            output, output_artifacts, output_truncated, output_missing = self._select_output(
                agent, output_dir, output_file, stdout, redactor
            )
            latency = time.monotonic() - start

            if timed_out:
                return (
                    AdapterResult(
                        status=CellStatus.timeout,
                        exit_code=proc.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        output=output,
                        output_artifacts=[str(path) for path in output_artifacts],
                        latency_s=latency,
                        failure_mode="timeout",
                        timed_out=True,
                        stdout_truncated=stdout_truncated,
                        stderr_truncated=stderr_truncated,
                        output_truncated=output_truncated,
                        trace_id=trace_id,
                    ),
                    redactor,
                )
            if output_missing:
                return (
                    AdapterResult(
                        status=CellStatus.error,
                        exit_code=proc.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        output=output,
                        output_artifacts=[],
                        latency_s=latency,
                        failure_mode="output_file_missing",
                        stdout_truncated=stdout_truncated,
                        stderr_truncated=stderr_truncated,
                        output_truncated=output_truncated,
                        trace_id=trace_id,
                    ),
                    redactor,
                )
            if proc.returncode != 0:
                return (
                    AdapterResult(
                        status=CellStatus.error,
                        exit_code=proc.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        output=output,
                        output_artifacts=[str(path) for path in output_artifacts],
                        latency_s=latency,
                        failure_mode=f"exit_code_{proc.returncode}",
                        stdout_truncated=stdout_truncated,
                        stderr_truncated=stderr_truncated,
                        output_truncated=output_truncated,
                        trace_id=trace_id,
                    ),
                    redactor,
                )
            return (
                AdapterResult(
                    status=CellStatus.passed,
                    exit_code=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    output=output,
                    output_artifacts=[str(path) for path in output_artifacts],
                    latency_s=latency,
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                    output_truncated=output_truncated,
                    trace_id=trace_id,
                ),
                redactor,
            )
        except FileNotFoundError as exc:
            latency = time.monotonic() - start
            return (
                AdapterResult(
                    status=CellStatus.error,
                    output="",
                    stderr=redactor.redact(str(exc)),
                    latency_s=latency,
                    failure_mode="command_not_found",
                    trace_id=trace_id,
                ),
                redactor,
            )

    def _build_argv(
        self,
        agent: AgentSpec,
        output_dir: Path,
        output_file: Path,
        input_file: Path,
    ) -> list[str]:
        replacements = {
            "{output_dir}": str(output_dir),
            "{output_file}": str(output_file),
            "{input_file}": str(input_file),
            "{python}": sys.executable,
        }
        argv: list[str] = []
        for arg in agent.command:
            value = arg
            for placeholder, replacement in replacements.items():
                value = value.replace(placeholder, replacement)
            argv.append(value)
        if not argv:
            raise AdapterError("agent command cannot be empty")
        return argv

    def _build_env(
        self,
        agent: AgentSpec,
        output_dir: Path,
        output_file: Path,
        trace_id: str,
    ) -> tuple[dict[str, str], Redactor]:
        env = {key: value for key, value in os.environ.items() if key in self.inherited_env_keys}
        env.update(agent.env)
        redaction_values = {
            key: value
            for key, value in os.environ.items()
            if key.startswith("MICRO_EVAL_SECRET_")
        }
        redaction_values.update(agent.env)
        for name in agent.required_secrets:
            if name not in os.environ:
                raise AdapterError(f"required secret missing from environment: {name}")
            env[name] = os.environ[name]
            redaction_values[name] = os.environ[name]
        env["MICRO_EVAL_OUTPUT_DIR"] = str(output_dir)
        env["MICRO_EVAL_OUTPUT_FILE"] = str(output_file)
        env["MICRO_EVAL_TRACE_ID"] = trace_id
        return env, Redactor(redaction_values)

    async def _read_limited(self, stream: asyncio.StreamReader | None) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False
        chunks: list[bytes] = []
        retained = 0
        truncated = False
        while True:
            chunk = await stream.read(8192)
            if not chunk:
                break
            remaining = self.output_cap_bytes - retained
            if remaining > 0:
                chunks.append(chunk[:remaining])
                retained += min(len(chunk), remaining)
            if len(chunk) > remaining:
                truncated = True
        return b"".join(chunks), truncated

    def _select_output(
        self,
        agent: AgentSpec,
        output_dir: Path,
        output_file: Path,
        stdout: str,
        redactor: Redactor,
    ) -> tuple[str, list[Path], bool, bool]:
        if agent.output_mode == OutputMode.stdout:
            return stdout, [], False, False
        if agent.output_mode == OutputMode.file:
            if output_file.is_symlink():
                output_file.unlink(missing_ok=True)
                return f"[linked output file skipped: {output_file.name}]", [], False, True
            if not output_file.exists():
                return "", [], False, True
            if not self._is_safe_regular_output(output_file, output_dir.resolve()):
                return f"[linked output file skipped: {output_file.name}]", [], False, True
            text, truncated = self._redact_text_file(output_file, redactor)
            return text, [output_file], truncated, False
        if agent.output_mode == OutputMode.directory:
            parts: list[str] = []
            artifacts: list[Path] = []
            truncated = False
            root = output_dir.resolve()
            for path in sorted(output_dir.rglob("*")):
                if path.name in {"input.txt", "stdout.txt", "stderr.txt"}:
                    continue
                if path.is_symlink():
                    path.unlink(missing_ok=True)
                    parts.append(f"[symlink artifact skipped: {path.name}]")
                    continue
                if not path.is_file():
                    continue
                try:
                    file_stat = path.lstat()
                    real_path = path.resolve(strict=True)
                except OSError:
                    parts.append(f"[artifact skipped: {path.name}]")
                    continue
                if (
                    not stat.S_ISREG(file_stat.st_mode)
                    or file_stat.st_nlink > 1
                    or not _is_relative_to(real_path, root)
                ):
                    path.unlink(missing_ok=True)
                    parts.append(f"[linked artifact skipped: {path.name}]")
                    continue
                artifacts.append(path)
                try:
                    text, was_truncated = self._redact_text_file(path, redactor)
                    truncated = truncated or was_truncated
                    parts.append(text)
                except OSError:
                    parts.append(str(path))
            return stdout or "\n".join(parts), artifacts, truncated, False
        return stdout, [], False, False

    def _redact_text_file(self, path: Path, redactor: Redactor) -> tuple[str, bool]:
        data = path.read_bytes()
        truncated = len(data) > self.output_cap_bytes
        retained = data[: self.output_cap_bytes]
        if looks_binary(retained):
            return f"[binary artifact skipped: {path.name}]", truncated
        text = retained.decode(errors="replace")
        redacted = redactor.redact(text)
        path.write_text(redacted)
        return redacted, truncated

    def _is_safe_regular_output(self, path: Path, root: Path) -> bool:
        try:
            file_stat = path.lstat()
            real_path = path.resolve(strict=True)
        except OSError:
            return False
        if path.is_symlink() or not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink > 1:
            path.unlink(missing_ok=True)
            return False
        if not _is_relative_to(real_path, root):
            path.unlink(missing_ok=True)
            return False
        return True

    build_env = _build_env


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
