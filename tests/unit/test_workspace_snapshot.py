"""Tests for engine/workspace.py — snapshot, diff, cleanup, and toolchain coverage.

Targets the uncovered lines identified by the coverage report:
  62, 65, 68, 72, 76, 80-84, 117-118, 145-166, 179-183,
  247, 250-261, 264-275, 280, 306-308, 314, 316-317,
  349, 355, 357, 359, 361, 363, 366, 376-377, 392-393, 405-406
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from micro_eval.engine.providers.base import IsolationLevel, WorkspaceHandle
from micro_eval.engine.workspace import (
    WorkspaceError,
    WorkspaceManager,
    _git_commit,
    _git_dirty,
    _run_git,
    build_same_start_snapshot,
    evaluate_snapshot_gate,
    resolve_git_commit,
)
from micro_eval.models.environment import CellSnapshot, SameStartSnapshot
from micro_eval.models.task import (
    FixtureSource,
    TaskSpec,
    ToolchainSpec,
    WorkspaceSpec,
    WorkspaceType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(path: Path) -> Path:
    """Initialise a minimal git repo with one commit and return its path."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "file.txt").write_text("content")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "add", "file.txt"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=T", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return path


def _minimal_snapshot_kwargs(*, project_root: Path, tasks: list[TaskSpec]) -> dict:
    return dict(
        project_root=project_root,
        tasks=tasks,
        config_hash="abc123",
        configuration_digests={"cfg": "d1"},
        task_revisions={"t1": "r1"},
        python_version="3.11.0",
        guardrails_digest="g0",
        timestamp="2026-06-15T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# WorkspaceManager construction — provider registry branches (lines 62-84)
# ---------------------------------------------------------------------------


class TestWorkspaceManagerConstruction:
    def test_manager_initialises_with_git_repo(self, tmp_path: Path) -> None:
        """WorkspaceManager can be constructed in any directory (no crash on init)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="test-init")
        assert mgr.project_root == repo
        assert mgr.run_id == "test-init"

    def test_manager_uses_adhoc_run_id_when_none(self, tmp_path: Path) -> None:
        """run_id defaults to 'adhoc' when not provided."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo)
        assert mgr.run_id == "adhoc"

    def test_registry_property_returns_registry(self, tmp_path: Path) -> None:
        """registry property exposes the ProviderRegistry (line 72)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="reg-test")
        # ProviderRegistry is always present
        registry = mgr.registry
        assert registry is not None

    def test_default_provider_property(self, tmp_path: Path) -> None:
        """_default_provider returns the GitWorktreeProvider (line 76)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="dp-test")
        provider = mgr._default_provider
        assert provider.name == "git_worktree"

    def test_create_legacy_workspace_returns_path(self, tmp_path: Path) -> None:
        """create() (legacy compatibility shim, lines 78-84) returns a valid path."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="create-test")
        ws_path = mgr.create(suffix="eval")
        assert ws_path.exists()
        mgr.cleanup()


# ---------------------------------------------------------------------------
# WorkspaceManager.prepare — isolation level degradation (lines 95-133)
# ---------------------------------------------------------------------------


class TestPrepareDegradation:
    def test_os_policy_degrades_to_logical_when_unavailable(self, tmp_path: Path) -> None:
        """prepare() degrades os_policy → logical with caveat when no OS provider found (lines 100-107)."""
        from micro_eval.models.task import IsolationLevel as TaskIsolationLevel

        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="degrade-test")

        # Remove all os_policy providers from the registry to simulate an unsupported platform.
        # Keep only the git_worktree (logical) provider.
        from micro_eval.engine.providers.git_worktree import GitWorktreeProvider
        from micro_eval.engine.providers.base import ProviderRegistry

        new_registry = ProviderRegistry()
        new_registry.register(GitWorktreeProvider(repo))
        mgr._registry = new_registry

        caveats: list[str] = []
        spec = WorkspaceSpec(type=WorkspaceType.blank, isolation_level=TaskIsolationLevel.os_policy)
        prepared = mgr.prepare(cell_id="degrade-cell", workspace=spec, caveats=caveats)

        assert prepared.path.exists()
        # The caveat must mention degradation.
        assert any("os_policy" in c and "logical" in c for c in caveats)
        mgr.cleanup()

    def test_prepare_raises_when_no_provider_for_level(self, tmp_path: Path) -> None:
        """prepare() raises WorkspaceError when no provider is available and level is not os_policy (line 109-113)."""
        from micro_eval.models.task import IsolationLevel as TaskIsolationLevel
        from micro_eval.engine.providers.base import ProviderRegistry

        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="no-provider")

        # Clear registry so nothing handles container-level.
        mgr._registry = ProviderRegistry()

        spec = WorkspaceSpec(type=WorkspaceType.blank, isolation_level=TaskIsolationLevel.container)
        with pytest.raises(WorkspaceError, match="No provider available"):
            mgr.prepare(cell_id="no-prov-cell", workspace=spec)


# ---------------------------------------------------------------------------
# WorkspaceManager.cleanup_workspace — failure swallowing (lines 117-118, 145-166)
# ---------------------------------------------------------------------------


class TestCleanupWorkspace:
    def test_cleanup_failure_is_swallowed_and_recorded(self, tmp_path: Path) -> None:
        """Cleanup failure must be swallowed and recorded in CellSnapshot (lines 158-166)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="cleanup-fail-test")

        # Create a real blank workspace.
        prepared = mgr.prepare(cell_id="cleanup-fail-cell", workspace=WorkspaceSpec(type=WorkspaceType.blank))

        # Remove the handle to force the shutil.rmtree path (else path in else branch, lines 154-157).
        prepared.handle = None
        prepared.source_repo = None
        prepared.cleanup_kind = "project_workspace"

        # Patch shutil.rmtree to fail on the first call (triggers cleanup_failed branch).
        # On the second call (ignore_errors=True fallback, lines 163-166), let it succeed.
        original_rmtree = __import__("shutil").rmtree

        call_count = 0

        def failing_rmtree(path, ignore_errors=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1 and not ignore_errors:
                raise OSError("synthetic cleanup failure")
            return original_rmtree(path, ignore_errors=True)

        with patch("shutil.rmtree", side_effect=failing_rmtree):
            snapshot = mgr.cleanup_workspace(prepared)

        assert snapshot.cleanup_status == "cleanup_failed"
        assert snapshot.cleanup_error is not None
        assert "synthetic cleanup failure" in snapshot.cleanup_error

    def test_cleanup_failure_inner_exception_is_silenced(self, tmp_path: Path) -> None:
        """Even if the fallback rmtree raises too, no exception propagates (lines 165-166)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="double-fail")
        prepared = mgr.prepare(cell_id="df-cell", workspace=WorkspaceSpec(type=WorkspaceType.blank))
        prepared.handle = None
        prepared.source_repo = None
        prepared.cleanup_kind = "project_workspace"

        # Both rmtree calls fail.
        with patch("shutil.rmtree", side_effect=OSError("always fails")):
            snapshot = mgr.cleanup_workspace(prepared)  # must not raise

        assert snapshot.cleanup_status == "cleanup_failed"

    def test_cleanup_success_sets_cleaned_status(self, tmp_path: Path) -> None:
        """Successful cleanup sets cleanup_status='cleaned' (line 137)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="cleanup-ok-test")
        prepared = mgr.prepare(cell_id="ok-cell", workspace=WorkspaceSpec(type=WorkspaceType.blank))
        snapshot = mgr.cleanup_workspace(prepared)
        assert snapshot.cleanup_status == "cleaned"
        assert snapshot.cleanup_error is None

    def test_cleanup_via_provider_handle(self, tmp_path: Path) -> None:
        """cleanup_workspace calls provider.cleanup() when handle is set (lines 141-143)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="handle-cleanup")
        prepared = mgr.prepare(cell_id="handle-cell", workspace=WorkspaceSpec(type=WorkspaceType.blank))
        # handle should be set for git_worktree provider
        assert prepared.handle is not None
        snapshot = mgr.cleanup_workspace(prepared)
        assert snapshot.cleanup_status == "cleaned"

    def test_cleanup_git_worktree_path_without_handle(self, tmp_path: Path) -> None:
        """Cleanup uses legacy git worktree path when handle is None (lines 147-153)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="legacy-cleanup")
        prepared = mgr.prepare(cell_id="legacy-cell", workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)))
        # Simulate the legacy path: strip the handle to force legacy cleanup code.
        prepared.handle = None
        prepared.cleanup_kind = "git_worktree"
        prepared.source_repo = repo
        snapshot = mgr.cleanup_workspace(prepared)
        assert snapshot.cleanup_status == "cleaned"

    def test_cleanup_with_handle_but_no_registry_provider_falls_back_to_rmtree(self, tmp_path: Path) -> None:
        """When handle is set but no provider is registered for its level, shutil.rmtree is used (lines 144-146)."""
        from micro_eval.engine.providers.base import ProviderRegistry

        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="rmtree-fallback")
        prepared = mgr.prepare(cell_id="rmtree-cell", workspace=WorkspaceSpec(type=WorkspaceType.blank))

        # Swap in an empty registry so select() returns None for the handle's level.
        mgr._registry = ProviderRegistry()

        assert prepared.handle is not None
        assert prepared.path.exists()
        snapshot = mgr.cleanup_workspace(prepared)
        # Path should be gone and status should be 'cleaned' (rmtree succeeded).
        assert not prepared.path.exists()
        assert snapshot.cleanup_status == "cleaned"

    def test_prepare_workspace_provider_error_becomes_workspace_error(self, tmp_path: Path) -> None:
        """WorkspaceProviderError raised by provider.create() is re-wrapped as WorkspaceError (lines 117-118)."""
        from micro_eval.engine.providers.git_worktree import WorkspaceProviderError as ProviderError
        from micro_eval.engine.providers.base import ProviderRegistry, IsolationLevel as BIsolationLevel
        from unittest.mock import MagicMock

        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="prov-err")

        # Replace the git_worktree provider with a mock that raises WorkspaceProviderError.
        mock_provider = MagicMock()
        mock_provider.supported_levels = [BIsolationLevel.logical]
        mock_provider.create.side_effect = ProviderError("simulated provider failure")

        registry = ProviderRegistry()
        registry.register(mock_provider)
        mgr._registry = registry

        spec = WorkspaceSpec(type=WorkspaceType.blank)
        with pytest.raises(WorkspaceError, match="simulated provider failure"):
            mgr.prepare(cell_id="err-cell", workspace=spec)


# ---------------------------------------------------------------------------
# WorkspaceManager.collect_diff (lines 177-183)
# ---------------------------------------------------------------------------


class TestCollectDiff:
    def test_collect_diff_clean_worktree_returns_none(self, tmp_path: Path) -> None:
        """collect_diff() returns None for a clean git worktree (line 181)."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="diff-clean")
        result = mgr.collect_diff(repo)
        assert result is None

    def test_collect_diff_dirty_worktree_returns_diff_string(self, tmp_path: Path) -> None:
        """collect_diff() returns a non-empty string for a dirty worktree (line 181)."""
        repo = _make_git_repo(tmp_path / "project")
        # Modify a tracked file to make the worktree dirty.
        (repo / "file.txt").write_text("modified content")
        mgr = WorkspaceManager(repo, run_id="diff-dirty")
        result = mgr.collect_diff(repo)
        assert result is not None
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_collect_diff_non_git_directory_returns_none(self, tmp_path: Path) -> None:
        """collect_diff() returns None for a non-git directory (graceful degradation, line 182-183)."""
        non_git = tmp_path / "not_a_repo"
        non_git.mkdir()
        (non_git / "file.txt").write_text("hello")
        mgr = WorkspaceManager(tmp_path, run_id="diff-nongit")
        result = mgr.collect_diff(non_git)
        assert result is None


# ---------------------------------------------------------------------------
# _run_git — error branches (lines 392-393, 405-406)
# ---------------------------------------------------------------------------


class TestRunGit:
    def test_run_git_check_false_returns_failed_result(self, tmp_path: Path) -> None:
        """_run_git with check=False returns even on non-zero exit (line 392-393)."""
        non_git = tmp_path / "nope"
        non_git.mkdir()
        result = _run_git(["status"], cwd=non_git, check=False)
        assert result.returncode != 0

    def test_run_git_check_true_raises_workspace_error_on_failure(self, tmp_path: Path) -> None:
        """_run_git with check=True raises WorkspaceError on non-zero exit (lines 405-406)."""
        non_git = tmp_path / "nope2"
        non_git.mkdir()
        with pytest.raises(WorkspaceError):
            _run_git(["status"], cwd=non_git, check=True)

    def test_run_git_raises_workspace_error_when_git_not_found(self, tmp_path: Path) -> None:
        """_run_git raises WorkspaceError('git executable not found') (lines 392-393)."""
        repo = _make_git_repo(tmp_path / "r")
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            with pytest.raises(WorkspaceError, match="git executable not found"):
                _run_git(["status"], cwd=repo, check=False)


# ---------------------------------------------------------------------------
# _git_commit / _git_dirty helpers (lines 376-377, 382-385)
# ---------------------------------------------------------------------------


class TestGitHelpers:
    def test_git_commit_returns_hash_for_valid_repo(self, tmp_path: Path) -> None:
        """_git_commit returns the HEAD commit hash for a valid git repo."""
        repo = _make_git_repo(tmp_path / "r")
        commit = _git_commit(repo)
        assert commit is not None
        assert len(commit) == 40  # SHA-1 hex

    def test_git_commit_returns_none_for_non_git_dir(self, tmp_path: Path) -> None:
        """_git_commit returns None when not in a git repo (line 384-385)."""
        non_git = tmp_path / "ng"
        non_git.mkdir()
        result = _git_commit(non_git)
        assert result is None

    def test_git_dirty_returns_false_for_clean_repo(self, tmp_path: Path) -> None:
        """_git_dirty returns False for a clean repo."""
        repo = _make_git_repo(tmp_path / "r")
        result = _git_dirty(repo)
        assert result is False

    def test_git_dirty_returns_true_for_dirty_repo(self, tmp_path: Path) -> None:
        """_git_dirty returns True when there are uncommitted changes (lines 376-377)."""
        repo = _make_git_repo(tmp_path / "r")
        (repo / "file.txt").write_text("dirty change")
        result = _git_dirty(repo)
        assert result is True

    def test_git_dirty_returns_none_for_non_git_dir(self, tmp_path: Path) -> None:
        """_git_dirty returns None for a non-git directory (line 392-393)."""
        non_git = tmp_path / "ng"
        non_git.mkdir()
        result = _git_dirty(non_git)
        assert result is None


# ---------------------------------------------------------------------------
# resolve_git_commit (lines 371-378)
# ---------------------------------------------------------------------------


class TestResolveGitCommit:
    def test_resolves_head_when_ref_is_none(self, tmp_path: Path) -> None:
        """resolve_git_commit resolves HEAD when ref is None (line 373)."""
        repo = _make_git_repo(tmp_path / "r")
        commit = resolve_git_commit(repo, ref=None)
        assert len(commit) == 40

    def test_raises_for_nonexistent_ref(self, tmp_path: Path) -> None:
        """resolve_git_commit raises WorkspaceError for a bad ref (lines 376-377)."""
        repo = _make_git_repo(tmp_path / "r")
        with pytest.raises(WorkspaceError, match="Failed to resolve git ref"):
            resolve_git_commit(repo, ref="nonexistent-branch-xyz")


# ---------------------------------------------------------------------------
# build_same_start_snapshot — toolchain fingerprint (lines 247, 264-275)
# ---------------------------------------------------------------------------


class TestToolchainFingerprint:
    def _task(self, task_id: str, *, project_root: Path, toolchain: ToolchainSpec) -> TaskSpec:
        return TaskSpec(
            id=task_id,
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(
                type=WorkspaceType.blank,
                toolchain=toolchain,
            ),
        )

    def test_toolchain_with_runtime_produces_deterministic_fingerprint(self, tmp_path: Path) -> None:
        """A runtime declaration produces a non-None, deterministic fingerprint (lines 264-266)."""
        project = tmp_path / "project"
        project.mkdir()
        task = self._task("t1", project_root=project, toolchain=ToolchainSpec(runtime="python3.11"))
        snap1 = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        snap2 = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert snap1.toolchain_fingerprint is not None
        assert snap1.toolchain_fingerprint == snap2.toolchain_fingerprint

    def test_toolchain_fingerprint_changes_when_runtime_changes(self, tmp_path: Path) -> None:
        """Changing the runtime value changes the toolchain fingerprint."""
        project = tmp_path / "project"
        project.mkdir()
        task_a = self._task("t1", project_root=project, toolchain=ToolchainSpec(runtime="python3.11"))
        task_b = self._task("t1", project_root=project, toolchain=ToolchainSpec(runtime="python3.12"))
        snap_a = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task_a]))
        snap_b = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task_b]))
        assert snap_a.toolchain_fingerprint != snap_b.toolchain_fingerprint

    def test_toolchain_with_lockfile_produces_fingerprint(self, tmp_path: Path) -> None:
        """A lockfile declaration whose file exists is hashed into the fingerprint (lines 267-274)."""
        project = tmp_path / "project"
        project.mkdir()
        lockfile = project / "requirements.lock"
        lockfile.write_text("numpy==1.26.0\n")
        task = self._task("t1", project_root=project, toolchain=ToolchainSpec(lockfile="requirements.lock"))
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert snap.toolchain_fingerprint is not None

    def test_toolchain_lockfile_outside_root_adds_caveat(self, tmp_path: Path) -> None:
        """A lockfile path escaping the project root adds a caveat, not a crash (lines 269-275)."""
        project = tmp_path / "project"
        project.mkdir()
        task = self._task("t1", project_root=project, toolchain=ToolchainSpec(lockfile="../outside.lock"))
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert any("lockfile path rejected" in c for c in snap.caveats)

    def test_no_toolchain_fingerprint_when_none_declared(self, tmp_path: Path) -> None:
        """No toolchain declared → toolchain_fingerprint is None (line 300)."""
        project = tmp_path / "project"
        project.mkdir()
        task = TaskSpec(id="t1", name="Task", input_payload="")
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert snap.toolchain_fingerprint is None


# ---------------------------------------------------------------------------
# build_same_start_snapshot — fixture digests (lines 250-261)
# ---------------------------------------------------------------------------


class TestFixtureDigests:
    def test_fixture_with_explicit_digest_uses_provided_digest(self, tmp_path: Path) -> None:
        """A fixture with a provided digest stores that value verbatim (line 252)."""
        project = tmp_path / "project"
        project.mkdir()
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(
                type=WorkspaceType.blank,
                fixtures=[FixtureSource(path="data.txt", digest="precomputed-digest-abc")],
            ),
        )
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert snap.fixture_digests.get("t1:data.txt") == "precomputed-digest-abc"

    def test_fixture_without_digest_is_hashed_from_file(self, tmp_path: Path) -> None:
        """A fixture without a digest is hashed from the actual file contents (lines 254-259)."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "fixture.txt").write_text("fixture data")
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(
                type=WorkspaceType.blank,
                fixtures=[FixtureSource(path="fixture.txt")],
            ),
        )
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert "t1:fixture.txt" in snap.fixture_digests
        assert len(snap.fixture_digests["t1:fixture.txt"]) == 64  # SHA-256 hex

    def test_fixture_digest_is_deterministic(self, tmp_path: Path) -> None:
        """Fixture digest from file content is stable across two calls with same content."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "fixture.txt").write_text("stable content")
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(
                type=WorkspaceType.blank,
                fixtures=[FixtureSource(path="fixture.txt")],
            ),
        )
        kwargs = _minimal_snapshot_kwargs(project_root=project, tasks=[task])
        snap1 = build_same_start_snapshot(**kwargs)
        snap2 = build_same_start_snapshot(**kwargs)
        assert snap1.fixture_digests == snap2.fixture_digests

    def test_fixture_outside_root_adds_caveat(self, tmp_path: Path) -> None:
        """A fixture path escaping the project root adds a caveat (lines 260-261)."""
        project = tmp_path / "project"
        project.mkdir()
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(
                type=WorkspaceType.blank,
                fixtures=[FixtureSource(path="../outside.txt")],
            ),
        )
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert any("fixture path rejected" in c for c in snap.caveats)


# ---------------------------------------------------------------------------
# build_same_start_snapshot — mixed isolation / network policies (lines 247, 306-308, 314, 316-317)
# ---------------------------------------------------------------------------


class TestMixedPolicies:
    def test_mixed_isolation_levels_produce_caveat(self, tmp_path: Path) -> None:
        """Tasks with different isolation levels set sandbox_policy='mixed' and add a caveat (lines 306-308)."""
        from micro_eval.models.task import IsolationLevel as TIsolationLevel

        project = tmp_path / "project"
        project.mkdir()
        task_a = TaskSpec(
            id="t-logical",
            name="T-Logical",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.blank, isolation_level=TIsolationLevel.logical),
        )
        task_b = TaskSpec(
            id="t-os",
            name="T-OS",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.blank, isolation_level=TIsolationLevel.os_policy),
        )
        kwargs = _minimal_snapshot_kwargs(project_root=project, tasks=[task_a, task_b])
        kwargs["task_revisions"] = {"t-logical": "r1", "t-os": "r2"}
        snap = build_same_start_snapshot(**kwargs)
        assert snap.sandbox_policy == "mixed"
        assert any("mixed isolation" in c for c in snap.caveats)

    def test_single_isolation_level_no_mixed_caveat(self, tmp_path: Path) -> None:
        """All tasks sharing isolation level → sandbox_policy is that level (lines 304-305)."""
        from micro_eval.models.task import IsolationLevel as TIsolationLevel

        project = tmp_path / "project"
        project.mkdir()
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.blank, isolation_level=TIsolationLevel.logical),
        )
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert snap.sandbox_policy == "logical"
        assert not any("mixed isolation" in c for c in snap.caveats)

    def test_mixed_network_policies_produce_caveat(self, tmp_path: Path) -> None:
        """Tasks with different network policies add a caveat (lines 314-317)."""
        from micro_eval.models.task import NetworkPolicy

        project = tmp_path / "project"
        project.mkdir()
        task_a = TaskSpec(
            id="t-full",
            name="T-Full",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.blank, network_policy=NetworkPolicy.full),
        )
        task_b = TaskSpec(
            id="t-none",
            name="T-None",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.blank, network_policy=NetworkPolicy.none),
        )
        kwargs = _minimal_snapshot_kwargs(project_root=project, tasks=[task_a, task_b])
        kwargs["task_revisions"] = {"t-full": "r1", "t-none": "r2"}
        snap = build_same_start_snapshot(**kwargs)
        assert snap.network_policy == "mixed"
        assert any("mixed network" in c for c in snap.caveats)

    def test_single_network_policy_stored(self, tmp_path: Path) -> None:
        """A single network policy is stored in network_policy field (line 313-314)."""
        from micro_eval.models.task import NetworkPolicy

        project = tmp_path / "project"
        project.mkdir()
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.blank, network_policy=NetworkPolicy.none),
        )
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert snap.network_policy == "none"
        assert not any("mixed network" in c for c in snap.caveats)

    def test_blank_workspace_no_git_commit(self, tmp_path: Path) -> None:
        """blank workspace tasks produce workspace_commits[id]=None (lines 293-294)."""
        project = tmp_path / "project"
        project.mkdir()
        task = TaskSpec(id="t1", name="Task", input_payload="")
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=project, tasks=[task]))
        assert snap.git_commit is None

    def test_relative_git_repo_path_resolved_against_project_root(self, tmp_path: Path) -> None:
        """A relative git_repo path in WorkspaceSpec is resolved against project_root (line 280)."""
        # Use the project root as the git repo and refer to it via a relative sub-path.
        repo = _make_git_repo(tmp_path / "project")
        # Create a sub-directory inside the repo that is NOT a git repo itself.
        # Instead, we point workspace path to "." (relative, resolves to project root).
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path="."),
        )
        snap = build_same_start_snapshot(**_minimal_snapshot_kwargs(project_root=repo, tasks=[task]))
        # Relative "." resolves to project_root which is a valid git repo; should produce a commit.
        assert snap.git_commit is not None


# ---------------------------------------------------------------------------
# evaluate_snapshot_gate (lines 341-368)
# ---------------------------------------------------------------------------


class TestEvaluateSnapshotGate:
    def _intended(self, **kwargs) -> SameStartSnapshot:
        defaults = dict(
            workspace_type="blank",
            git_commit=None,
            dirty=False,
            config_hash="abc123",
            configuration_digests={},
            task_revisions={},
            python_version="3.11.0",
            guardrails_digest="g0",
            timestamp="2026-06-15T00:00:00+00:00",
        )
        defaults.update(kwargs)
        return SameStartSnapshot(**defaults)

    def _cell(self, **kwargs) -> CellSnapshot:
        defaults = dict(
            workspace_path="/tmp/ws",
            git_commit=None,
            dirty=False,
            setup_exit_code=None,
            cleanup_status=None,
        )
        defaults.update(kwargs)
        return CellSnapshot(**defaults)

    def test_none_intended_returns_warn(self) -> None:
        """Missing intended snapshot → status='warn' (line 349)."""
        observed = self._cell()
        result = evaluate_snapshot_gate(None, observed)
        assert result.status == "warn"
        assert "same_start_snapshot" in result.mismatch_fields

    def test_matching_snapshots_return_pass(self, tmp_path: Path) -> None:
        """Matching intended and observed snapshots → status='pass'."""
        repo = _make_git_repo(tmp_path / "r")
        commit = _git_commit(repo)
        intended = self._intended(git_commit=commit, dirty=False)
        observed = self._cell(git_commit=commit, dirty=False, setup_exit_code=0)
        result = evaluate_snapshot_gate(intended, observed)
        assert result.status == "pass"
        assert not result.mismatch_fields

    def test_commit_mismatch_in_workspace_map_produces_warn(self, tmp_path: Path) -> None:
        """Commit mismatch via workspace_map adds 'workspace_map' to mismatches (line 355, 357)."""
        repo = _make_git_repo(tmp_path / "r")
        commit = _git_commit(repo)
        intended = self._intended(
            git_commit=None,
            workspace_map={"t1": "commit-aaa"},
        )
        observed = self._cell(git_commit="commit-bbb")
        result = evaluate_snapshot_gate(intended, observed, task_id="t1")
        assert result.status == "warn"
        assert "workspace_map" in result.mismatch_fields

    def test_commit_mismatch_without_workspace_map_produces_warn(self, tmp_path: Path) -> None:
        """Commit mismatch without workspace_map adds 'git_commit' to mismatches (line 357)."""
        intended = self._intended(git_commit="commit-aaa")
        observed = self._cell(git_commit="commit-bbb")
        result = evaluate_snapshot_gate(intended, observed)
        assert result.status == "warn"
        assert "git_commit" in result.mismatch_fields

    def test_dirty_mismatch_produces_warn(self) -> None:
        """Dirty flag mismatch adds 'dirty' to mismatches (line 359)."""
        intended = self._intended(dirty=False)
        observed = self._cell(dirty=True)
        result = evaluate_snapshot_gate(intended, observed)
        assert result.status == "warn"
        assert "dirty" in result.mismatch_fields

    def test_setup_exit_code_nonzero_produces_mismatch(self) -> None:
        """Non-zero setup_exit_code adds 'setup_exit_code' to mismatches (line 361)."""
        intended = self._intended()
        observed = self._cell(setup_exit_code=1)
        result = evaluate_snapshot_gate(intended, observed)
        assert result.status == "warn"
        assert "setup_exit_code" in result.mismatch_fields

    def test_cleanup_failed_adds_caveat_not_mismatch(self) -> None:
        """cleanup_failed adds a caveat (line 363) but is not a mismatch field."""
        intended = self._intended()
        observed = self._cell(cleanup_status="cleanup_failed")
        result = evaluate_snapshot_gate(intended, observed)
        # The caveat must mention cleanup.
        assert any("cleanup" in c for c in result.caveats)
        # cleanup_failed is not listed as a mismatch field.
        assert "cleanup_failed" not in result.mismatch_fields

    def test_task_id_without_matching_workspace_map_entry_falls_back_to_git_commit(self) -> None:
        """task_id not in workspace_map falls back to intended.git_commit (line 355-356)."""
        intended = self._intended(
            git_commit="commit-aaa",
            workspace_map={"other-task": "commit-bbb"},
        )
        observed = self._cell(git_commit="commit-aaa")
        result = evaluate_snapshot_gate(intended, observed, task_id="t1")
        assert result.status == "pass"
