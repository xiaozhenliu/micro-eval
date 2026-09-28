"""Workspace preparation, snapshots, and cleanup."""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from micro_eval.engine.git_refs import GitRefResolutionError, resolve_commit
from micro_eval.engine.command import resolve_command_argv
from micro_eval.engine.execution import ExecutionContext
from micro_eval.engine.providers.base import ExecutionRequest, IsolationLevel, ProviderRegistry, WorkspaceHandle
from micro_eval.engine.providers.git_worktree import GitWorktreeProvider, WorkspaceProviderError
from micro_eval.engine.providers.os_policy import BubblewrapProvider, SeatbeltProvider
from micro_eval.engine.providers.remote import E2BProvider, ModalProvider
from micro_eval.models.environment import (
    CellSnapshot,
    SameStartSnapshot,
    SnapshotGateResult,
    WorkspaceObservation,
)
from micro_eval.models.ids import canonical_digest, safe_path_segment
from micro_eval.models.task import TaskSpec, WorkspaceSpec, WorkspaceType


class WorkspaceError(Exception):
    """Raised when workspace operations fail."""


class GitRefWorkspaceError(WorkspaceError):
    """Ref resolution failure with a stable machine-readable cause."""

    def __init__(self, message: str, *, reason: str) -> None:
        self.reason = reason
        super().__init__(message)


async def _finish_shielded(task: asyncio.Task, *, propagate: bool = False):
    """Finish resource ownership work even if cancellation arrives again."""
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            cancelled = True
            if task.done():
                result = task.result()
                break
    if cancelled and propagate:
        raise asyncio.CancelledError
    return result


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
    execution_context: ExecutionContext | None = None


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

        if caveats is not None and handle.provider_name in {"seatbelt", "bubblewrap"}:
            caveats.append(
                f"{handle.provider_name} applies OS policy to setup, agent and command validation; "
                "host-readable files are not confidential; timeout/cancel cleanup covers only "
                "descendants that remain in the owned process group"
            )
        if caveats is not None and handle.provider_name in {"e2b", "modal"}:
            caveats.append(
                f"{handle.provider_name} executes in a dedicated remote sandbox; "
                "SDK contract tests do not prove cloud network or termination guarantees; "
                "live validation is optional and remote workspace observation is unavailable"
            )

        if handle.is_remote:
            snapshot = CellSnapshot(
                workspace_path=str(handle.workspace_path),
                setup_exit_code=handle.setup_exit_code,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        else:
            snapshot = self.collect_cell_snapshot(
                handle.workspace_path, setup_exit_code=handle.setup_exit_code,
                cleanup_status=None,
            )
        prepared = PreparedWorkspace(
            path=handle.workspace_path,
            snapshot=snapshot,
            cleanup_kind="git_worktree" if handle.source_repo else "project_workspace",
            source_repo=handle.source_repo,
            handle=handle,
            execution_context=ExecutionContext(provider, handle),
        )
        self._prepared.append(prepared)
        return prepared

    async def prepare_async(
        self, *, cell_id: str, workspace: WorkspaceSpec, output_dir: Path,
        caveats: list[str] | None = None,
    ) -> PreparedWorkspace:
        """Materialize first, then run setup through the selected executor.

        A canceled creator is joined before cleanup: abandoning a worker thread
        would otherwise leak a remote sandbox created after cancellation.
        """
        creation = asyncio.create_task(asyncio.to_thread(
            self.prepare, cell_id=cell_id,
            workspace=workspace.model_copy(update={"setup": []}), caveats=caveats,
        ))
        prepared = None
        try:
            prepared = await asyncio.shield(creation)
            context = prepared.execution_context
            if context is None:
                raise WorkspaceError("provider did not create an execution context")
            await context.prepare_output(output_dir)
            if workspace.setup:
                for command in workspace.setup:
                    argv = resolve_command_argv(command, replacements={"{python}": context.python_executable})
                    env = {} if context.is_remote else {
                        key: value for key, value in os.environ.items()
                        if key in GitWorktreeProvider.SETUP_ENV_KEYS
                    }
                    result = await context.execute(ExecutionRequest(
                        argv=argv, cwd=prepared.path, env=env, timeout_s=300,
                        output_cap_bytes=64 * 1024,
                    ))
                    prepared.handle.setup_exit_code = result.exit_code
                    prepared.snapshot.setup_exit_code = result.exit_code
                    if result.timed_out or result.exit_code != 0:
                        raise WorkspaceError(f"workspace setup failed: exit_code={result.exit_code}; {result.stderr}")
                if not context.is_remote:
                    prepared.snapshot = self.collect_cell_snapshot(
                        prepared.path, setup_exit_code=prepared.handle.setup_exit_code,
                        cleanup_status=None,
                    )
                    if prepared.snapshot.dirty:
                        prepared.handle.metadata["setup_modified"] = "true"
            return prepared
        except BaseException as exc:
            if prepared is None:
                try:
                    prepared = await _finish_shielded(creation)
                except Exception:
                    pass
            if prepared is not None:
                await self.cleanup_workspace_async(prepared)
                if isinstance(exc, Exception):
                    exc.prepared_workspace = prepared
            raise

    async def cleanup_workspace_async(self, prepared: PreparedWorkspace) -> CellSnapshot:
        task = asyncio.create_task(asyncio.to_thread(self.cleanup_workspace, prepared))
        return await _finish_shielded(task, propagate=True)

    def cleanup_workspace(self, prepared: PreparedWorkspace) -> CellSnapshot:
        """Cleanup one workspace and return the updated snapshot facts."""
        status = "cleaned"
        error: str | None = None
        if prepared.snapshot.cleanup_status == "cleaned":
            return prepared.snapshot
        try:
            if prepared.execution_context is not None:
                prepared.execution_context.provider.cleanup(prepared.execution_context.handle)
            elif prepared.handle is not None:
                raise WorkspaceError("workspace handle has no owning execution context")
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
            from micro_eval.engine.adapter import Redactor
            error = Redactor.from_env().redact(str(exc))
        finally:
            if prepared.execution_context is not None:
                try:
                    prepared.execution_context.cleanup_staging()
                except Exception as exc:
                    from micro_eval.engine.adapter import Redactor
                    status = "cleanup_failed"
                    error = Redactor.from_env().redact(str(exc))
        prepared.snapshot.cleanup_status = status
        prepared.snapshot.cleanup_error = error
        return prepared.snapshot

    def cleanup(self) -> None:
        """Remove all created workspaces."""
        for prepared in list(self._prepared):
            self.cleanup_workspace(prepared)
        self._prepared.clear()

    def observe_final(self, prepared: PreparedWorkspace, *, byte_limit: int) -> WorkspaceObservation:
        """Collect raw, bounded facts before any validator can mutate the workspace."""
        if prepared.handle is None:
            workspace_type = WorkspaceType.blank
            return WorkspaceObservation(
                workspace_type=workspace_type,
                warnings=("observation_unavailable",),
            )
        provider = prepared.execution_context.provider if prepared.execution_context else None
        if provider is None:
            return WorkspaceObservation(
                workspace_type=prepared.handle.workspace_type,
                warnings=("observation_unavailable",),
            )
        try:
            return provider.observe_final(prepared.handle, byte_limit=max(0, byte_limit))
        except Exception as exc:  # noqa: BLE001 - preserve a normal result with an explicit caveat.
            return WorkspaceObservation(
                workspace_type=prepared.handle.workspace_type,
                warnings=(f"observation_failed:{exc.__class__.__name__}",),
            )

    def collect_diff(self, worktree_path: Path) -> Optional[str]:
        """Legacy raw-diff helper retained for ad-hoc callers."""
        handle = WorkspaceHandle(
            workspace_path=worktree_path,
            provider_name="git_worktree",
            isolation_level=IsolationLevel.logical,
            workspace_type=WorkspaceType.git_repo,
        )
        return self._git_worktree_provider.observe_final(
            handle, byte_limit=50 * 1024 * 1024
        ).diff_text

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
            except WorkspaceError as exc:
                workspace_commits[task.id] = None
                workspace_dirty[task.id] = None
                caveats.append(f"[task={task.id}] {exc}")
                continue
            # A ref that cannot be resolved to a commit is a plan error, not
            # a caveat: silently downgrading it would let a run start from an
            # unknown commit (GRO-972).
            try:
                commit = resolve_git_commit(source, task.workspace.ref)
            except GitRefWorkspaceError as exc:
                raise GitRefWorkspaceError(f"[task={task.id}] {exc}", reason=exc.reason) from exc
            except WorkspaceError as exc:
                # A source that is not a usable git repository keeps the
                # existing caveat policy; source diagnostics belong to the
                # workspace source validation (GRO-576), not ref resolution.
                workspace_commits[task.id] = None
                workspace_dirty[task.id] = None
                caveats.append(f"[task={task.id}] {exc}")
                continue
            workspace_commits[task.id] = commit
            workspace_dirty[task.id] = _git_dirty(source)
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
    """Resolve a git ref to an immutable commit hash.

    Strict resolution (GRO-972): the ref may not be interpreted as a git
    option and must resolve to exactly one commit object; tags are peeled to
    their commit. Ref-specific failures raise :class:`GitRefWorkspaceError`;
    a source that is not a git repository stays a generic
    :class:`WorkspaceError` so existing source-validation paths keep their
    own diagnostics.
    """
    try:
        return resolve_commit(ref, repo=repo)
    except GitRefResolutionError as exc:
        if exc.reason == GitRefResolutionError.REASON_NOT_A_REPOSITORY:
            raise WorkspaceError(str(exc)) from exc
        raise GitRefWorkspaceError(str(exc), reason=exc.reason) from exc


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
