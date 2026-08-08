"""GitWorktreeProvider: Level 0 (logical) isolation via git worktrees."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from micro_eval.engine.command import resolve_command_argv
from micro_eval.engine.providers.base import (
    CommandResult,
    IsolationLevel,
    WorkspaceHandle,
    WorkspaceProvider,
)
from micro_eval.models.artifact import ArtifactRef
from micro_eval.models.ids import safe_path_segment
from micro_eval.models.task import WorkspaceSpec, WorkspaceType


class GitWorktreeProvider:
    """Level 0 isolation: git worktrees / blank / file-copy workspaces.

    This provider encapsulates the original WorkspaceManager logic for
    creating isolated directories via git worktree, blank dirs, or file copies.
    """

    SETUP_ENV_KEYS = {
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
    }

    @property
    def name(self) -> str:
        return "git_worktree"

    @property
    def supported_levels(self) -> list[IsolationLevel]:
        return [IsolationLevel.logical]

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
        workspace_root = self._project_root / ".micro-eval" / "workspaces" / safe_path_segment(run_id)
        safe_cell = safe_path_segment(cell_id)
        source_repo: Path | None = None

        if spec.type == WorkspaceType.git_repo:
            source_repo = self._resolve_source_path(spec.path)
            workspace_path = self._create_git_worktree(source_repo, spec.ref, safe_cell, workspace_root)
        elif spec.type == WorkspaceType.files:
            workspace_path = self._create_local_workspace_dir(safe_cell, workspace_root)
            self._copy_files(spec, workspace_path)
        else:
            workspace_path = self._create_local_workspace_dir(safe_cell, workspace_root)

        if spec.setup:
            self._run_setup(spec.setup, workspace_path)

        return WorkspaceHandle(
            workspace_path=workspace_path,
            provider_name=self.name,
            isolation_level=IsolationLevel.logical,
            source_repo=source_repo,
        )

    def exec_command(
        self,
        handle: WorkspaceHandle,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> CommandResult:
        if not argv or not all(isinstance(a, str) and a for a in argv):
            raise ValueError("exec_command requires a non-empty argv list of non-empty strings")
        try:
            result = subprocess.run(
                argv,
                cwd=handle.workspace_path,
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
            return CommandResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(exit_code=-1, timed_out=True)

    def collect_artifacts(self, handle: WorkspaceHandle) -> list[ArtifactRef]:
        return []

    def collect_diff(self, handle: WorkspaceHandle) -> str | None:
        try:
            result = subprocess.run(
                ["git", "diff", "--no-color"],
                cwd=handle.workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout if result.stdout.strip() else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def snapshot(self, handle: WorkspaceHandle) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=handle.workspace_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    def restore(self, handle: WorkspaceHandle, snap: str) -> None:
        raise NotImplementedError("restore not supported for git worktree provider")

    def cleanup(self, handle: WorkspaceHandle) -> None:
        if handle.source_repo is not None:
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(handle.workspace_path)],
                    cwd=handle.source_repo,
                    capture_output=True,
                    check=True,
                )
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=handle.source_repo,
                    capture_output=True,
                    check=False,
                )
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        shutil.rmtree(handle.workspace_path, ignore_errors=True)

    def _resolve_source_path(self, path_value: str | None) -> Path:
        source = Path(path_value) if path_value else self._project_root
        if not source.is_absolute():
            source = self._project_root / source
        source = source.resolve()
        _assert_within_root(source, self._project_root)
        if not source.exists():
            raise WorkspaceProviderError(f"Workspace source does not exist: {source}")
        if not _is_git_repo(source):
            raise WorkspaceProviderError(f"Workspace source is not a git repository: {source}")
        return source

    def _create_local_workspace_dir(self, safe_cell: str, workspace_root: Path) -> Path:
        workspace_path = workspace_root / safe_cell
        if workspace_path.exists():
            raise WorkspaceProviderError(f"Workspace path already exists: {workspace_path}")
        workspace_path.mkdir(parents=True)
        return workspace_path

    def _create_git_worktree(
        self, source_repo: Path, ref: str | None, safe_cell: str, workspace_root: Path
    ) -> Path:
        commit = _resolve_git_commit(source_repo, ref)
        workspace_path = workspace_root / safe_cell
        if workspace_path.exists():
            raise WorkspaceProviderError(f"Workspace path already exists: {workspace_path}")
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(workspace_path), commit],
            cwd=source_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return workspace_path

    def _copy_files(self, workspace: WorkspaceSpec, workspace_path: Path) -> None:
        paths = workspace.files or ([workspace.path] if workspace.path else [])
        for item in paths:
            source = Path(item)
            if not source.is_absolute():
                source = self._project_root / source
            source = source.resolve()
            _assert_within_root(source, self._project_root)
            if not source.exists():
                raise WorkspaceProviderError(f"Workspace file source does not exist: {source}")
            destination = workspace_path / source.name
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    def _run_setup(self, setup: list[list[str]], workspace_path: Path) -> int:
        exit_code = 0
        for command in setup:
            if not command or any(not isinstance(part, str) or not part for part in command):
                raise WorkspaceProviderError("workspace setup commands must be non-empty argv lists")
            result = subprocess.run(
                resolve_command_argv(command),
                cwd=workspace_path,
                env={key: value for key, value in os.environ.items() if key in self.SETUP_ENV_KEYS},
                capture_output=True,
                text=True,
                check=False,
            )
            exit_code = result.returncode
            if exit_code != 0:
                break
        return exit_code


class WorkspaceProviderError(Exception):
    """Raised when a workspace provider operation fails."""


def _assert_within_root(source: Path, root: Path) -> None:
    try:
        source.relative_to(root)
    except ValueError:
        raise WorkspaceProviderError(
            f"Workspace source path escapes the project root: {source} "
            f"(project root: {root})"
        )


def _is_git_repo(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _resolve_git_commit(repo: Path, ref: str | None) -> str:
    target = ref or "HEAD"
    try:
        result = subprocess.run(
            ["git", "rev-parse", target],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise WorkspaceProviderError(
            f"Failed to resolve git ref {target!r} in {repo}"
        ) from exc
