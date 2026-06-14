"""Workspace preparation, snapshots, and cleanup."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from micro_eval.engine.providers.base import IsolationLevel, ProviderRegistry, WorkspaceHandle
from micro_eval.engine.providers.git_worktree import GitWorktreeProvider, WorkspaceProviderError
from micro_eval.engine.providers.os_policy import BubblewrapProvider, SeatbeltProvider
from micro_eval.engine.providers.remote import E2BProvider, ModalProvider
from micro_eval.models.environment import CellSnapshot, SameStartSnapshot, SnapshotGateResult
from micro_eval.models.ids import canonical_digest, safe_path_segment
from micro_eval.models.task import TaskSpec, WorkspaceSpec, WorkspaceType


class WorkspaceError(Exception):
    """Raised when workspace operations fail."""


def _assert_within_root(source: Path, root: Path) -> None:
    """Reject a resolved source path that escapes the project root."""
    try:
        source.relative_to(root)
    except ValueError:
        raise WorkspaceError(
            f"Workspace source path escapes the project root: {source} "
            f"(project root: {root})"
        )


@dataclass
class PreparedWorkspace:
    """Workspace facts for one RunCell."""

    path: Path
    snapshot: CellSnapshot
    cleanup_kind: str
    source_repo: Path | None = None
    handle: WorkspaceHandle | None = None


class WorkspaceManager:
    """Manages isolated task workspaces via provider registry."""

    def __init__(self, project_root: Path | str, *, run_id: str | None = None):
        self.project_root = Path(project_root).resolve()
        self.run_id = run_id or "adhoc"
        self.workspace_root = self.project_root / ".micro-eval" / "workspaces" / safe_path_segment(self.run_id)
        self._prepared: list[PreparedWorkspace] = []
        self._git_worktree_provider = GitWorktreeProvider(self.project_root)
        self._registry = ProviderRegistry()
        self._registry.register(self._git_worktree_provider)
        seatbelt = SeatbeltProvider(self.project_root)
        if seatbelt.supported_levels:
            self._registry.register(seatbelt)
        bubblewrap = BubblewrapProvider(self.project_root)
        if bubblewrap.supported_levels:
            self._registry.register(bubblewrap)
        e2b = E2BProvider(self.project_root)
        if e2b.supported_levels:
            self._registry.register(e2b)
        modal = ModalProvider(self.project_root)
        if modal.supported_levels:
            self._registry.register(modal)

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    @property
    def _default_provider(self) -> GitWorktreeProvider:
        return self._git_worktree_provider

    def create(self, suffix: str = "eval") -> Path:
        """Create a legacy git-worktree workspace for compatibility."""
        prepared = self.prepare(
            cell_id=suffix,
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(self.project_root)),
        )
        return prepared.path

    def prepare(
        self, *, cell_id: str, workspace: WorkspaceSpec, caveats: list[str] | None = None,
    ) -> PreparedWorkspace:
        """Create an isolated workspace and collect its pre-agent snapshot.

        If the requested isolation_level is os_policy but no OS policy provider
        is available on this platform, degrades to logical with a caveat.
        Higher levels (container/vm) never degrade locally — they fail hard.
        """
        import platform as _platform

        isolation_level = workspace.isolation_level
        provider = self._registry.select(isolation_level)

        if provider is None and isolation_level == IsolationLevel.os_policy:
            provider = self._registry.select(IsolationLevel.logical)
            caveat = (
                f"requested isolation os_policy unavailable on {_platform.system()}; "
                f"ran at logical"
            )
            if caveats is not None:
                caveats.append(caveat)

        if provider is None:
            raise WorkspaceError(
                f"No provider available for isolation level '{isolation_level.value}'. "
                f"Registered providers: {[p.name for p in self._registry.providers]}"
            )

        try:
            handle = provider.create(workspace, cell_id=cell_id, run_id=self.run_id)
        except WorkspaceProviderError as exc:
            raise WorkspaceError(str(exc)) from exc

        snapshot = self.collect_cell_snapshot(
            handle.workspace_path,
            setup_exit_code=None,
            cleanup_status=None,
        )
        prepared = PreparedWorkspace(
            path=handle.workspace_path,
            snapshot=snapshot,
            cleanup_kind="git_worktree" if handle.source_repo else "project_workspace",
            source_repo=handle.source_repo,
            handle=handle,
        )
        self._prepared.append(prepared)
        return prepared

    def cleanup_workspace(self, prepared: PreparedWorkspace) -> CellSnapshot:
        """Cleanup one workspace and return the updated snapshot facts."""
        status = "cleaned"
        error: str | None = None
        try:
            if prepared.handle is not None:
                provider = self._registry.select(prepared.handle.isolation_level)
                if provider is not None:
                    provider.cleanup(prepared.handle)
                else:
                    import shutil
                    shutil.rmtree(prepared.path, ignore_errors=False)
            elif prepared.cleanup_kind == "git_worktree" and prepared.source_repo is not None:
                _run_git(
                    ["worktree", "remove", "--force", str(prepared.path)],
                    cwd=prepared.source_repo,
                    check=True,
                )
                _run_git(["worktree", "prune"], cwd=prepared.source_repo, check=False)
            else:
                import shutil

                shutil.rmtree(prepared.path, ignore_errors=False)
        except Exception as exc:  # noqa: BLE001 - cleanup failure is recorded for evidence.
            status = "cleanup_failed"
            error = str(exc)
            try:
                import shutil

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
            result = _run_git(["diff", "--no-color"], cwd=worktree_path, check=True)
            return result.stdout if result.stdout.strip() else None
        except WorkspaceError:
            return None

    def _resolve_source_path(self, path_value: str | None) -> Path:
        """Delegate to provider for containment-guarded source resolution."""
        try:
            return self._git_worktree_provider._resolve_source_path(path_value)
        except WorkspaceProviderError as exc:
            raise WorkspaceError(str(exc)) from exc

    def _copy_files(self, workspace: WorkspaceSpec, workspace_path: Path) -> None:
        """Delegate to provider for containment-guarded file copy."""
        try:
            self._git_worktree_provider._copy_files(workspace, workspace_path)
        except WorkspaceProviderError as exc:
            raise WorkspaceError(str(exc)) from exc

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

    # Collect isolation/network policy for comparability dimensions
    isolation_levels: set[str] = set()
    network_policies: set[str] = set()
    fixture_digests: dict[str, str] = {}
    toolchain_parts: list[str] = []

    for task in tasks:
        isolation_levels.add(task.workspace.isolation_level.value)
        if task.workspace.network_policy is not None:
            network_policies.add(task.workspace.network_policy.value)

        for fixture in task.workspace.fixtures:
            if fixture.digest:
                fixture_digests[f"{task.id}:{fixture.path}"] = fixture.digest
            else:
                fixture_path = (root / fixture.path).resolve()
                try:
                    _assert_within_root(fixture_path, root)
                    if fixture_path.exists():
                        fixture_digests[f"{task.id}:{fixture.path}"] = canonical_digest(
                            fixture_path.read_text(errors="replace")
                        )
                except WorkspaceError as exc:
                    caveats.append(f"[task={task.id}] fixture path rejected: {exc}")

        if task.workspace.toolchain:
            if task.workspace.toolchain.runtime:
                toolchain_parts.append(f"runtime:{task.workspace.toolchain.runtime}")
            if task.workspace.toolchain.lockfile:
                lockfile_path = (root / task.workspace.toolchain.lockfile).resolve()
                try:
                    _assert_within_root(lockfile_path, root)
                    if lockfile_path.exists():
                        toolchain_parts.append(
                            f"lockfile:{task.workspace.toolchain.lockfile}:{canonical_digest(lockfile_path.read_text(errors='replace'))}"
                        )
                except WorkspaceError as exc:
                    caveats.append(f"[task={task.id}] lockfile path rejected: {exc}")

        if task.workspace.type == WorkspaceType.git_repo:
            source = Path(task.workspace.path) if task.workspace.path else root
            if not source.is_absolute():
                source = root / source
            source = source.resolve()
            try:
                _assert_within_root(source, root)
                commit = resolve_git_commit(source, task.workspace.ref)
                dirty = _git_dirty(source)
            except WorkspaceError as exc:
                commit = None
                dirty = None
                caveats.append(f"[task={task.id}] {exc}")
            workspace_commits[task.id] = commit
            workspace_dirty[task.id] = dirty
        else:
            workspace_commits[task.id] = None
            workspace_dirty[task.id] = None

    unique_commits = {value for value in workspace_commits.values() if value is not None}
    unique_dirty = {value for value in workspace_dirty.values() if value is not None}
    setup_commands = [task.workspace.setup for task in tasks if task.workspace.setup]

    toolchain_fingerprint = canonical_digest(sorted(toolchain_parts)) if toolchain_parts else None

    # Determine sandbox_policy and network_policy for snapshot comparability
    sandbox_policy: str | None = None
    if len(isolation_levels) == 1:
        sandbox_policy = next(iter(isolation_levels))
    elif len(isolation_levels) > 1:
        sandbox_policy = "mixed"
        caveats.append(
            f"mixed isolation levels in run: {sorted(isolation_levels)}; results may not be comparable"
        )

    network_policy_value: str | None = None
    if len(network_policies) == 1:
        network_policy_value = next(iter(network_policies))
    elif len(network_policies) > 1:
        network_policy_value = "mixed"
        caveats.append(
            f"mixed network policies in run: {sorted(network_policies)}; results may not be comparable"
        )

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
        sandbox_policy=sandbox_policy,
        network_policy=network_policy_value,
        toolchain_fingerprint=toolchain_fingerprint,
        fixture_digests=fixture_digests,
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
