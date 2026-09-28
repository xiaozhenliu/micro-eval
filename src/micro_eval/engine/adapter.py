"""Safe argv-based agent adapter."""

from __future__ import annotations

import asyncio
import os
import stat
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING

from micro_eval.engine.command import resolve_command_argv
from micro_eval.engine.process_runner import read_limited, run_process
from micro_eval.engine.providers.base import ExecutionRequest
from micro_eval.models.configuration import AgentSpec, InputMode, OutputMode
from micro_eval.models.ids import looks_binary
from micro_eval.models.run import AdapterResult, CellStatus


if TYPE_CHECKING:
    from micro_eval.engine.execution import ExecutionContext


class AdapterError(Exception):
    """Raised when adapter setup fails before process execution."""


class Redactor:
    """Named text redactor for declared environment values."""

    SECRET_ENV_PREFIX = "MICRO_EVAL_SECRET_"

    def __init__(self, values: dict[str, str]):
        self.values: dict[str, str] = {name: value for name, value in values.items() if value}

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Redactor":
        """Build a redactor from declared MICRO_EVAL_SECRET_* environment values."""
        source = env if env is not None else dict(os.environ)
        values = {key: value for key, value in source.items() if key.startswith(cls.SECRET_ENV_PREFIX)}
        return cls(values)

    def redact(self, text: str) -> str:
        for name, value in self.values.items():
            if text == value:
                return f"[REDACTED:{name}]"
        redacted = text
        for name, value in sorted(self.values.items(), key=lambda item: -len(item[1])):
            redacted = redacted.replace(value, f"[REDACTED:{name}]")
        return redacted

    def redact_bounded(self, text: str, *, truncated: bool, cap_bytes: int) -> str:
        """Redact complete secrets and any secret prefix at a truncated boundary."""
        if truncated:
            # A prefix cut off by a byte cap is still secret material. Remove it
            # before full-value substitution so no partial credential survives.
            text = text.rstrip("\ufffd")
            suffix_start = len(text)
            for value in self.values.values():
                for length in range(min(len(value) - 1, len(text)), 0, -1):
                    if text.endswith(value[:length]):
                        suffix_start = min(suffix_start, len(text) - length)
                        break
            if suffix_start < len(text):
                text = text[:suffix_start] + "[REDACTED]"
        return self.redact(text).encode()[:cap_bytes].decode(errors="ignore")


class AgentAdapter:
    """Invoke agents through their workspace execution context."""

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
        if output_cap_bytes < 0:
            raise ValueError("output_cap_bytes cannot be negative")
        self.output_cap_bytes = output_cap_bytes

    async def invoke(
        self,
        *,
        agent: AgentSpec,
        input_payload: str,
        cwd: Path,
        output_dir: Path,
        trace_id: str = "",
        execution_context: ExecutionContext | None = None,
    ) -> tuple[AdapterResult, Redactor]:
        """Execute through the workspace owner and normalize bounded output."""
        output_dir.mkdir(parents=True, exist_ok=True)
        with ExitStack() as temporary:
            receive_dir = Path(temporary.enter_context(tempfile.TemporaryDirectory(
                prefix=".micro-eval-receive-", dir=output_dir.parent,
            )))
            execution_output = (
                await execution_context.prepare_output(output_dir)
                if execution_context is not None else
                Path(temporary.enter_context(tempfile.TemporaryDirectory(
                    prefix=".micro-eval-execute-", dir=output_dir.parent,
                )))
            )
            return await self._invoke_prepared(
                agent=agent, input_payload=input_payload, cwd=cwd,
                output_dir=output_dir, trace_id=trace_id, execution_context=execution_context,
                execution_output=execution_output, receive_dir=receive_dir,
            )

    async def _invoke_prepared(
        self,
        *,
        agent: AgentSpec,
        input_payload: str,
        cwd: Path,
        output_dir: Path,
        trace_id: str,
        execution_context: ExecutionContext | None,
        execution_output: Path,
        receive_dir: Path,
    ) -> tuple[AdapterResult, Redactor]:
        input_file = execution_output / "input.txt"
        output_file = execution_output / "output.txt"
        stdin_data: bytes | None = input_payload.encode()
        if agent.input_mode == InputMode.file:
            if execution_context is None:
                input_file.write_bytes(stdin_data)
            else:
                await execution_context.write_file(input_file, stdin_data)
            stdin_data = None

        env, redactor = self._build_env(
            agent, execution_output, output_file, trace_id,
            remote=execution_context is not None and execution_context.is_remote,
        )
        argv = self._build_argv(
            agent, execution_output, output_file, input_file,
            python_executable=(
                execution_context.python_executable if execution_context is not None else None
            ),
        )
        request = ExecutionRequest(
            argv=argv,
            cwd=execution_context.workspace_path if execution_context is not None else cwd,
            env=env,
            stdin=stdin_data,
            timeout_s=agent.timeout_s,
            output_cap_bytes=self.output_cap_bytes,
        )
        start = time.monotonic()
        try:
            command = (
                await execution_context.execute(request)
                if execution_context is not None
                else await run_process(request)
            )
            collected_truncated = False
            selection_dir = execution_output
            if execution_context is not None:
                collected_truncated = await execution_context.collect_output(
                    execution_output, receive_dir, self.output_cap_bytes
                )
                selection_dir = receive_dir
            stdout = redactor.redact_bounded(
                command.stdout, truncated=command.stdout_truncated, cap_bytes=self.output_cap_bytes
            )
            stderr = redactor.redact_bounded(
                command.stderr, truncated=command.stderr_truncated, cap_bytes=self.output_cap_bytes
            )
            output, output_artifacts, output_truncated, output_missing = self._select_output(
                agent, selection_dir, selection_dir / "output.txt", stdout, redactor,
                collected_truncated=collected_truncated,
            )
            transfer_warnings = getattr(execution_context, "output_warnings", ())
            if not output and agent.output_mode != OutputMode.stdout and transfer_warnings:
                output = redactor.redact_bounded(
                    "; ".join(transfer_warnings), truncated=False, cap_bytes=self.output_cap_bytes,
                )
            output_artifacts = _export_outputs(
                output_artifacts, selection_dir, output_dir, redactor
            )
            status = CellStatus.passed
            failure_mode = None
            if command.timed_out:
                status, failure_mode = CellStatus.timeout, "timeout"
            elif output_missing:
                status, failure_mode = CellStatus.error, "output_file_missing"
            elif command.exit_code != 0:
                status, failure_mode = CellStatus.error, f"exit_code_{command.exit_code}"
            return (
                AdapterResult(
                    status=status,
                    exit_code=command.exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    output=output,
                    output_artifacts=[str(path) for path in output_artifacts],
                    latency_s=time.monotonic() - start,
                    failure_mode=failure_mode,
                    timed_out=command.timed_out,
                    stdout_truncated=command.stdout_truncated,
                    stderr_truncated=command.stderr_truncated,
                    output_truncated=output_truncated or collected_truncated,
                    trace_id=trace_id,
                ),
                redactor,
            )
        except FileNotFoundError as exc:
            return (
                AdapterResult(
                    status=CellStatus.error,
                    output="",
                    stderr=redactor.redact_bounded(
                        str(exc), truncated=False, cap_bytes=self.output_cap_bytes
                    ),
                    latency_s=time.monotonic() - start,
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
        *,
        python_executable: str | None = None,
    ) -> list[str]:
        replacements = {
            "{output_dir}": str(output_dir),
            "{output_file}": str(output_file),
            "{input_file}": str(input_file),
        }
        if python_executable is not None:
            replacements["{python}"] = python_executable
        argv = resolve_command_argv(agent.command, replacements=replacements)
        if not argv:
            raise AdapterError("agent command cannot be empty")
        return argv

    def _build_env(
        self,
        agent: AgentSpec,
        output_dir: Path,
        output_file: Path,
        trace_id: str,
        *,
        remote: bool = False,
    ) -> tuple[dict[str, str], Redactor]:
        control_credentials = {
            "E2B_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
            "MICRO_EVAL_SECRET_E2B_API_KEY",
            "MICRO_EVAL_SECRET_MODAL_TOKEN_ID", "MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET",
        }
        forbidden = control_credentials.intersection(set(agent.env) | set(agent.required_secrets))
        if forbidden:
            raise AdapterError(
                "provider control credentials cannot be injected into an agent: "
                + ", ".join(sorted(forbidden))
            )
        inherited_keys = {"LANG", "LC_ALL"} if remote else self.inherited_env_keys
        env = {key: value for key, value in os.environ.items() if key in inherited_keys}
        env.update(agent.env)
        redaction_values = {
            key: value
            for key, value in os.environ.items()
            if key.startswith("MICRO_EVAL_SECRET_")
        }
        redaction_values.update({
            key: value
            for key, value in agent.env.items()
            if key.startswith(Redactor.SECRET_ENV_PREFIX)
        })
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
        return await read_limited(stream, self.output_cap_bytes)

    def _select_output(
        self,
        agent: AgentSpec,
        output_dir: Path,
        output_file: Path,
        stdout: str,
        redactor: Redactor,
        *,
        collected_truncated: bool = False,
    ) -> tuple[str, list[Path], bool, bool]:
        if agent.output_mode == OutputMode.stdout:
            return stdout, [], False, False
        if agent.output_mode == OutputMode.file:
            skipped = redactor.redact_bounded(
                f"[linked output file skipped: {output_file.name}]",
                truncated=False, cap_bytes=self.output_cap_bytes,
            )
            if output_file.is_symlink():
                output_file.unlink(missing_ok=True)
                return skipped, [], False, True
            if not output_file.exists():
                return "", [], False, True
            if not self._is_safe_regular_output(output_file, output_dir.resolve()):
                return skipped, [], False, True
            try:
                text, truncated, binary, size_bytes = self._sanitize_output_file(
                    output_file, redactor, source_truncated=collected_truncated,
                    complete_only=True,
                )
            except OSError:
                return skipped, [], False, True
            if size_bytes > self.output_cap_bytes:
                output_file.unlink(missing_ok=True)
                summary = f"[oversized binary artifact skipped: {output_file.name}]" if binary else text
                return redactor.redact_bounded(
                    summary, truncated=False, cap_bytes=self.output_cap_bytes,
                ), [], True, False
            if binary:
                artifact = _preserve_binary_output(output_file)
                return redactor.redact_bounded(
                    text.replace("binary artifact skipped", "binary redaction skipped"),
                    truncated=False, cap_bytes=self.output_cap_bytes,
                ), [artifact], truncated, False
            return text, [output_file], truncated, False
        if agent.output_mode == OutputMode.directory:
            combined = bytearray()
            artifacts: list[Path] = []
            truncated = collected_truncated
            remaining = self.output_cap_bytes
            root = output_dir.resolve()

            def append_part(text: str) -> None:
                nonlocal truncated
                part = (b"\n" if combined else b"") + text.encode()
                available = max(0, self.output_cap_bytes - len(combined))
                truncated |= len(part) > available
                combined.extend(part[:available])

            paths, scan_truncated = _scan_output_paths(output_dir)
            truncated |= scan_truncated
            for path in paths:
                if ".tmp" in path.relative_to(output_dir).parts:
                    continue
                if path.name in {"input.txt", "stdout.txt", "stderr.txt"}:
                    continue
                if path.is_symlink():
                    path.unlink(missing_ok=True)
                    append_part(redactor.redact(f"[symlink artifact skipped: {path.name}]"))
                    continue
                try:
                    file_stat = path.lstat()
                except OSError:
                    continue
                if stat.S_ISDIR(file_stat.st_mode):
                    continue
                if not self._is_safe_regular_output(path, root):
                    append_part(redactor.redact(f"[linked artifact skipped: {path.name}]"))
                    continue
                if remaining <= 0 or len(artifacts) >= 1024:
                    path.unlink(missing_ok=True)
                    truncated = True
                    continue
                try:
                    text, was_truncated, binary, size_bytes = self._sanitize_output_file(
                        path, redactor, cap_bytes=remaining,
                        source_truncated=collected_truncated,
                        complete_only=True,
                    )
                except OSError:
                    path.unlink(missing_ok=True)
                    truncated = True
                    continue
                truncated |= was_truncated
                if size_bytes > remaining:
                    path.unlink(missing_ok=True)
                    append_part(redactor.redact(f"[oversized artifact skipped: {path.name}]"))
                    truncated = True
                    continue
                if binary:
                    artifacts.append(_preserve_binary_output(path))
                    remaining -= size_bytes
                    append_part(redactor.redact(
                        text.replace("binary artifact skipped", "binary redaction skipped")
                    ))
                    continue
                artifacts.append(path)
                remaining -= len(text.encode())
                append_part(text)
            return stdout or combined.decode(errors="ignore"), artifacts, truncated, False
        return stdout, [], False, False

    def _redact_text_file(
        self,
        path: Path,
        redactor: Redactor,
        *,
        cap_bytes: int | None = None,
        source_truncated: bool = False,
    ) -> tuple[str, bool]:
        text, truncated, _, _ = self._sanitize_output_file(
            path, redactor, cap_bytes=cap_bytes, source_truncated=source_truncated
        )
        return text, truncated

    def _sanitize_output_file(
        self,
        path: Path,
        redactor: Redactor,
        *,
        cap_bytes: int | None = None,
        source_truncated: bool = False,
        complete_only: bool = False,
    ) -> tuple[str, bool, bool, int]:
        """Read only the bounded prefix and rewrite the same verified file descriptor."""
        cap = self.output_cap_bytes if cap_bytes is None else cap_bytes
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path, flags)
        with os.fdopen(fd, "r+b") as stream:
            file_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink > 1:
                raise OSError("output must be an unlinked regular file")
            data = stream.read(cap + 1)
            size_bytes = max(file_stat.st_size, len(data))
            truncated = source_truncated or len(data) > cap
            retained = data[:cap]
            if looks_binary(retained):
                return (
                    f"[binary artifact skipped: {path.name}]", truncated, True,
                    size_bytes,
                )
            redacted = redactor.redact_bounded(
                retained.decode(errors="replace"), truncated=truncated, cap_bytes=cap
            )
            if not complete_only or size_bytes <= cap:
                stream.seek(0)
                stream.write(redacted.encode())
                stream.truncate()
        return redacted, truncated, False, size_bytes

    def _is_safe_regular_output(self, path: Path, root: Path) -> bool:
        try:
            file_stat = path.lstat()
            real_path = path.resolve(strict=True)
        except OSError:
            return False
        if stat.S_ISDIR(file_stat.st_mode):
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


def _preserve_binary_output(path: Path) -> Path:
    """Keep binary output.txt away from the lifecycle's textual summary path."""
    if path.name != "output.txt":
        return path
    fd, destination = tempfile.mkstemp(prefix="output-binary-", suffix=".bin", dir=path.parent)
    os.close(fd)
    target = Path(destination)
    path.replace(target)
    return target


def _export_outputs(
    paths: list[Path], source: Path, destination: Path, redactor: Redactor,
) -> list[Path]:
    """Move only selected sanitized artifacts into the durable cell directory."""
    from micro_eval.engine.execution import _open_beneath

    exported: list[Path] = []
    for path in paths:
        relative = path.relative_to(source)
        target_relative = relative
        if any(value in relative.as_posix() for value in redactor.values.values()):
            # Inspect agent-controlled path segments only. The host's parent
            # directories must retain their real names, even for short secrets.
            fd, safe_name = tempfile.mkstemp(
                prefix="redacted-artifact-", suffix=".bin", dir=destination,
            )
            os.close(fd)
            target_relative = Path(Path(safe_name).name)
        target = destination / target_relative
        source_parent = (
            os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            if relative.parent == Path(".") else
            _open_beneath(source, relative.parent, os.O_RDONLY | os.O_DIRECTORY)
        )
        try:
            destination_parent = _ensure_directory_beneath(destination, target_relative.parent)
            try:
                os.replace(
                    path.name, target.name,
                    src_dir_fd=source_parent, dst_dir_fd=destination_parent,
                )
            finally:
                os.close(destination_parent)
        finally:
            os.close(source_parent)
        exported.append(target)
    return exported


def _ensure_directory_beneath(root: Path, relative: Path) -> int:
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
    except BaseException:
        os.close(parent)
        raise
    return parent


def _scan_output_paths(root: Path, entry_limit: int = 4096) -> tuple[list[Path], bool]:
    """Inspect at most one bounded batch of entries without traversing symlinks."""
    from micro_eval.engine.execution import _open_beneath

    paths: list[Path] = []
    pending = [root]
    skipped = False
    while pending:
        directory = pending.pop()
        try:
            fd = (
                os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                if directory == root else
                _open_beneath(root, directory.relative_to(root), os.O_RDONLY | os.O_DIRECTORY)
            )
            try:
                with os.scandir(fd) as entries:
                    for entry in entries:
                        path = directory / entry.name
                        paths.append(path)
                        if len(paths) >= entry_limit:
                            return sorted(paths), True
                        if entry.name != ".tmp" and entry.is_dir(follow_symlinks=False):
                            pending.append(path)
            finally:
                os.close(fd)
        except OSError:
            skipped = True
    return sorted(paths), skipped
