"""Workspace preparation, snapshots, and cleanup."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from micro_eval.models.environment import CellSnapshot, SameStartSnapshot, SnapshotGateResult
from micro_eval.models.ids import canonical_digest, safe_path_segment
from micro_eval.models.task import TaskSpec, WorkspaceSpec, WorkspaceType


class WorkspaceError(Exception):
    """Raised when workspace operations fail."""


@dataclass
class PreparedWorkspace:
    """Workspace facts for one RunCell."""

    path: Path
    snapshot: CellSnapshot
    cleanup_kind: str
    source_repo: Path | None = None


class WorkspaceManager:
    """Manages isolated task workspaces."""

    setup_env_keys = {
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SYSTEMROOT",
    }

    def __init__(self, project_root: Path | str, *, run_id: str | None = None):
        self.project_root = Path(project_root).resolve()
        self.run_id = run_id or "adhoc"
        self._prepared: list[PreparedWorkspace] = []

    def create(self, suffix: str = "eval") -> Path:
        """Create a legacy git-worktree workspace for compatibility."""
        prepared = self.prepare(
            cell_id=suffix,
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(self.project_root)),
        )
        return prepared.path

    def prepare(self, *, cell_id: str, workspace: WorkspaceSpec) -> PreparedWorkspace:
        """Create an isolated workspace and collect its pre-agent snapshot."""
        safe_cell = safe_path_segment(cell_id)
        setup_exit_code: int | None = None
        source_repo: Path | None = None

        if workspace.type == WorkspaceType.git_repo:
            source_repo = self._resolve_source_path(workspace.path)
            workspace_path = self._create_git_worktree(source_repo, workspace.ref, safe_cell)
            cleanup_kind = "git_worktree"
        elif workspace.type == WorkspaceType.files:
            workspace_path = Path(tempfile.mkdtemp(prefix=f"micro-eval-{safe_cell}-"))
            cleanup_kind = "temp_dir"
            self._copy_files(workspace, workspace_path)
        else:
            workspace_path = Path(tempfile.mkdtemp(prefix=f"micro-eval-{safe_cell}-"))
            cleanup_kind = "temp_dir"

        if workspace.setup:
            setup_exit_code = self._run_setup(workspace.setup, workspace_path)

        snapshot = self.collect_cell_snapshot(
            workspace_path,
            setup_exit_code=setup_exit_code,
            cleanup_status=None,
        )
        prepared = PreparedWorkspace(
            path=workspace_path,
            snapshot=snapshot,
            cleanup_kind=cleanup_kind,
            source_repo=source_repo,
        )
        self._prepared.append(prepared)
        return prepared

    def cleanup_workspace(self, prepared: PreparedWorkspace) -> CellSnapshot:
        """Cleanup one workspace and return the updated snapshot facts."""
        status = "cleaned"
        error: str | None = None
        try:
            if prepared.cleanup_kind == "git_worktree" and prepared.source_repo is not None:
                self._run_git(
                    ["worktree", "remove", "--force", str(prepared.path)],
                    cwd=prepared.source_repo,
                    check=True,
                )
                self._run_git(["worktree", "prune"], cwd=prepared.source_repo, check=False)
            else:
                shutil.rmtree(prepared.path, ignore_errors=False)
        except Exception as exc:  # noqa: BLE001 - cleanup failure is recorded for evidence.
            status = "cleanup_failed"
            error = str(exc)
            try:
                shutil.rmtree(prepared.path, ignore_errors=True)
            except Exception:
                pass
        prepared.snapshot.cleanup_status = status
        prepared.snapshot.cleanup_error = error
        return prepared.snapshot

    def cleanup(self) -> None:
        """Remove all created workspaces."""
        for prepared in list(self._prepared):
            self.cleanup_workspace(prepared)
        self._prepared.clear()

    def collect_diff(self, worktree_path: Path) -> Optional[str]:
        """Collect git diff from a worktree."""
        try:
            result = self._run_git(["diff", "--no-color"], cwd=worktree_path, check=True)
            return result.stdout if result.stdout.strip() else None
        except WorkspaceError:
            return None

    def collect_cell_snapshot(
        self,
        workspace_path: Path,
        *,
        setup_exit_code: int | None,
        cleanup_status: str | None,
    ) -> CellSnapshot:
        """Collect observed workspace facts for one cell."""
        commit = _git_commit(workspace_path)
        dirty = _git_dirty(workspace_path) if commit else None
        return CellSnapshot(
            workspace_path=str(workspace_path),
            git_commit=commit,
            dirty=dirty,
            setup_exit_code=setup_exit_code,
            timestamp=datetime.now(timezone.utc).isoformat(),
            cleanup_status=cleanup_status,
        )

    def _resolve_source_path(self, path_value: str | None) -> Path:
        source = Path(path_value) if path_value else self.project_root
        if not source.is_absolute():
            source = self.project_root / source
        source = source.resolve()
        if not source.exists():
            raise WorkspaceError(f"Workspace source does not exist: {source}")
        if _git_commit(source) is None:
            raise WorkspaceError(f"Workspace source is not a git repository: {source}")
        return source

    def _create_git_worktree(self, source_repo: Path, ref: str | None, safe_cell: str) -> Path:
        commit = resolve_git_commit(source_repo, ref)
        workspace_path = Path(tempfile.mkdtemp(prefix=f"micro-eval-{safe_cell}-"))
        workspace_path.rmdir()
        self._run_git(
            ["worktree", "add", "--detach", str(workspace_path), commit],
            cwd=source_repo,
            check=True,
        )
        return workspace_path

    def _copy_files(self, workspace: WorkspaceSpec, workspace_path: Path) -> None:
        paths = workspace.files or ([workspace.path] if workspace.path else [])
        for item in paths:
            source = Path(item)
            if not source.is_absolute():
                source = self.project_root / source
            source = source.resolve()
            if not source.exists():
                raise WorkspaceError(f"Workspace file source does not exist: {source}")
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
                raise WorkspaceError("workspace setup commands must be non-empty argv lists")
            result = subprocess.run(
                command,
                cwd=workspace_path,
                env={key: value for key, value in os.environ.items() if key in self.setup_env_keys},
                capture_output=True,
                text=True,
                check=False,
            )
            exit_code = result.returncode
            if exit_code != 0:
                break
        return exit_code

    def _run_git(self, args: list[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        return _run_git(args, cwd=cwd, check=check)


def build_same_start_snapshot(
    *,
    project_root: Path | str,
    tasks: list[TaskSpec],
    config_hash: str,
    configuration_digests: dict[str, str],
    task_revisions: dict[str, str],
    python_version: str,
    guardrails_digest: str,
    timestamp: str,
) -> SameStartSnapshot:
    """Resolve intended run-level comparable start facts."""
    root = Path(project_root).resolve()
    workspace_types = sorted({task.workspace.type.value for task in tasks}) or ["blank"]
    workspace_type = workspace_types[0] if len(workspace_types) == 1 else "mixed"
    workspace_commits: dict[str, str | None] = {}
    workspace_dirty: dict[str, bool | None] = {}
    caveats: list[str] = []

    for task in tasks:
        if task.workspace.type == WorkspaceType.git_repo:
            source = Path(task.workspace.path) if task.workspace.path else root
            if not source.is_absolute():
                source = root / source
            source = source.resolve()
            try:
                commit = resolve_git_commit(source, task.workspace.ref)
                dirty = _git_dirty(source)
            except WorkspaceError as exc:
                commit = None
                dirty = None
                caveats.append(str(exc))
            workspace_commits[task.id] = commit
            workspace_dirty[task.id] = dirty
        else:
            workspace_commits[task.id] = None
            workspace_dirty[task.id] = None

    unique_commits = {value for value in workspace_commits.values() if value is not None}
    unique_dirty = {value for value in workspace_dirty.values() if value is not None}
    setup_commands = [task.workspace.setup for task in tasks if task.workspace.setup]

    return SameStartSnapshot(
        workspace_type=workspace_type,
        git_commit=next(iter(unique_commits)) if len(unique_commits) == 1 else None,
        dirty=next(iter(unique_dirty)) if len(unique_dirty) == 1 else (None if not unique_dirty else True),
        config_hash=config_hash,
        configuration_digests=configuration_digests,
        task_revisions=task_revisions,
        python_version=python_version,
        setup_commands_digest=canonical_digest(setup_commands) if setup_commands else None,
        guardrails_digest=guardrails_digest,
        workspace_map=workspace_commits if len(unique_commits) > 1 or any(workspace_commits.values()) else None,
        timestamp=timestamp,
        caveats=caveats,
    )


def evaluate_snapshot_gate(
    intended: SameStartSnapshot | None,
    observed: CellSnapshot,
    *,
    task_id: str | None = None,
) -> SnapshotGateResult:
    """Compare intended same-start facts with observed cell facts."""
    if intended is None:
        return SnapshotGateResult(status="warn", mismatch_fields=["same_start_snapshot"], caveats=["missing same-start snapshot"])

    mismatches: list[str] = []
    caveats: list[str] = []
    expected_commit = intended.git_commit
    if task_id and intended.workspace_map and task_id in intended.workspace_map:
        expected_commit = intended.workspace_map[task_id]
    if expected_commit is not None and observed.git_commit != expected_commit:
        mismatches.append("workspace_map" if intended.workspace_map else "git_commit")
    if intended.dirty is not None and observed.dirty != intended.dirty:
        mismatches.append("dirty")
    if observed.setup_exit_code not in {None, 0}:
        mismatches.append("setup_exit_code")
    if observed.cleanup_status == "cleanup_failed":
        caveats.append("workspace cleanup failed; inspect cleanup_error")

    if mismatches:
        caveats.append("cell start snapshot differs from intended same-start snapshot")
    status = "warn" if mismatches or caveats else "pass"
    return SnapshotGateResult(status=status, mismatch_fields=mismatches, caveats=caveats)


def resolve_git_commit(repo: Path, ref: str | None = None) -> str:
    """Resolve a git ref to an immutable commit hash."""
    target = ref or "HEAD"
    try:
        result = _run_git(["rev-parse", target], cwd=repo, check=True)
    except WorkspaceError as exc:
        raise WorkspaceError(f"Failed to resolve git ref {target!r} in {repo}: {exc}") from exc
    return result.stdout.strip()


def _git_commit(repo: Path) -> str | None:
    try:
        return _run_git(["rev-parse", "HEAD"], cwd=repo, check=True).stdout.strip()
    except WorkspaceError:
        return None


def _git_dirty(repo: Path) -> bool | None:
    try:
        result = _run_git(["status", "--porcelain"], cwd=repo, check=True)
        return bool(result.stdout.strip())
    except WorkspaceError:
        return None


def _run_git(args: list[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise WorkspaceError("git executable not found") from exc
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        raise WorkspaceError(message)
    return result
