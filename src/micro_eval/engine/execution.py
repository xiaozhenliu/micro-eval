"""One cell's provider execution and filesystem boundary."""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from micro_eval.engine.providers.base import (
    CommandResult, ExecutionRequest, IsolationLevel, WorkspaceHandle, WorkspaceProvider,
)
from micro_eval.engine.providers.git_worktree import WorkspaceProviderError


class ExecutionContext:
    """Bind execution, I/O and cleanup to the provider that created the cell.

    Remote paths are opaque: only the provider may interpret them. Local
    policy output lives outside the observed worktree and outside run metadata.
    """

    def __init__(self, provider: WorkspaceProvider, handle: WorkspaceHandle) -> None:
        self.provider = provider
        self.handle = handle
        self.output_path: Path | None = None
        self._host_output: Path | None = None
        self._local_staging: Path | None = None
        self.output_warnings: list[str] = []

    @property
    def workspace_path(self) -> Path:
        return self.handle.workspace_path

    @property
    def is_remote(self) -> bool:
        return self.handle.is_remote

    @property
    def python_executable(self) -> str:
        return "python3" if self.is_remote else sys.executable

    async def prepare_output(self, host_output_dir: Path) -> Path:
        if self.output_path is not None:
            if self._host_output != host_output_dir:
                raise WorkspaceProviderError("execution output directory cannot change")
            return self.output_path
        host_output_dir.mkdir(parents=True, exist_ok=True)
        self._host_output = host_output_dir
        if self.is_remote:
            self.output_path = Path(await _owned_io(
                self.provider.prepare_output, self.handle, host_output_dir,
            ))
        else:
            self._local_staging = Path(tempfile.mkdtemp(
                prefix=".micro-eval-io-", dir=self.workspace_path.parent,
            )).resolve()
            self.output_path = self._local_staging
            (self.output_path / ".tmp").mkdir()
        self.handle.metadata["output_path"] = str(self.output_path)
        return self.output_path

    async def execute(self, request: ExecutionRequest) -> CommandResult:
        cwd = request.cwd or self.workspace_path
        if not self._within_execution_roots(cwd):
            raise WorkspaceProviderError("execution cwd escapes the cell workspace/output")
        env = request.env
        if self.handle.isolation_level == IsolationLevel.os_policy and self.output_path:
            env = dict(env or {})
            env.update({key: str(self.output_path / ".tmp") for key in ("TMPDIR", "TEMP", "TMP")})
        return await self.provider.execute(self.handle, replace(request, cwd=cwd, env=env))

    def create_conversation_bridge(self, *, agent, env: dict[str, str], turn_timeout_s: float):
        if self.handle.isolation_level != IsolationLevel.logical:
            raise WorkspaceProviderError("provider does not support conversational sessions")
        factory = getattr(self.provider, "create_conversation_bridge", None)
        if factory is None:
            raise WorkspaceProviderError("provider does not support conversational sessions")
        return factory(self.handle, agent=agent, env=env, turn_timeout_s=turn_timeout_s)

    async def write_file(self, path: Path, data: bytes) -> None:
        if not self._within_execution_roots(path):
            raise WorkspaceProviderError("execution file path escapes the cell")
        if self.is_remote:
            await _owned_io(self.provider.write_file, self.handle, path, data)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        with os.fdopen(fd, "wb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise WorkspaceProviderError("execution input is not a private regular file")
            stream.truncate(0)
            stream.write(data)

    async def path_exists(self, path: Path) -> bool:
        if not self._within_execution_roots(path):
            return False
        if self.is_remote:
            return await _owned_io(self.provider.path_exists, self.handle, path)
        return path.exists()

    async def collect_output(self, execution_output: Path, host_output: Path, byte_limit: int) -> bool:
        if execution_output != self.output_path or self._host_output is None:
            raise WorkspaceProviderError("output transfer does not match the cell context")
        if (host_output.parent != self._host_output.parent
                or not host_output.name.startswith(".micro-eval-receive-")
                or host_output.is_symlink()):
            raise WorkspaceProviderError("output transfer requires a private receiving directory")
        if self.is_remote:
            return await _owned_io(
                self.provider.collect_output, self.handle, execution_output, host_output, byte_limit,
            )
        if execution_output == host_output:
            return False
        return copy_bounded_outputs(execution_output, host_output, byte_limit, warnings=self.output_warnings)

    def cleanup_staging(self) -> None:
        if self._local_staging is not None:
            shutil.rmtree(self._local_staging)
            self._local_staging = None

    def _within_execution_roots(self, path: Path) -> bool:
        if ".." in path.parts:
            return False
        roots = [self.workspace_path]
        if self.output_path is not None:
            roots.append(self.output_path)
        candidate = path if self.is_remote else path.resolve()
        return any(candidate.is_relative_to(root if self.is_remote else root.resolve()) for root in roots)


async def _owned_io(function, *args):
    """Join an SDK I/O worker before the caller can destroy its sandbox."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        # Retrieve failures so a canceled caller does not leak an unhandled
        # worker exception. The provider still owns its bounded SDK timeout.
        if not task.cancelled():
            task.exception()
        raise


def copy_bounded_outputs(
    source: Path, destination: Path, byte_limit: int, *, warnings: list[str] | None = None,
) -> bool:
    """Copy only private regular files, never traversing agent-owned links.

    Each complete body and the aggregate are bounded. Oversized files are
    omitted rather than retaining partial secrets at a truncation boundary.
    """
    remaining = max(0, byte_limit)
    skipped = False
    count = 0
    pending = [source]
    while pending:
        base = pending.pop()
        with os.scandir(base) as entries:
            batch = []
            for entry in entries:
                count += 1
                if count > 4096:
                    return True
                batch.append(entry)
        for item in sorted(batch, key=lambda entry: entry.name):
            entry = Path(item.path)
            if item.name == ".tmp":
                continue
            if item.is_dir(follow_symlinks=False):
                pending.append(entry)
                continue
            if item.name == "input.txt":
                continue
            try:
                info = entry.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > remaining:
                    skipped = True
                    if warnings is not None:
                        linked = stat.S_ISLNK(info.st_mode) or info.st_nlink != 1
                        reason = "symlink artifact skipped" if stat.S_ISLNK(info.st_mode) else "linked artifact skipped"
                        if linked and reason not in warnings:
                            warnings.append(reason)
                        if linked and entry.relative_to(source) == Path("output.txt"):
                            if "linked output file skipped" not in warnings:
                                warnings.append("linked output file skipped")
                    continue
                if not entry.resolve().is_relative_to(source.resolve()):
                    skipped = True
                    continue
                fd = _open_beneath(source, entry.relative_to(source), os.O_RDONLY | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        skipped = True
                        continue
                    data = stream.read(remaining + 1)
                if len(data) > remaining:
                    skipped = True
                    continue
                target = destination / entry.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise WorkspaceProviderError("host output destination escapes cell")
                fd = _open_beneath(destination, entry.relative_to(source), os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK)
                with os.fdopen(fd, "wb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise WorkspaceProviderError("host output is not a private regular file")
                    stream.truncate(0)
                    stream.write(data)
                remaining -= len(data)
            except OSError:
                skipped = True
    return skipped


def _open_beneath(root: Path, relative: Path, flags: int) -> int:
    """Open each component relative to an owned directory without following links."""
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise WorkspaceProviderError("invalid output path")
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        return os.open(relative.name, flags | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    finally:
        os.close(parent)
