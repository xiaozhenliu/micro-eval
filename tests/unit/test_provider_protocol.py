"""Provider protocol contract tests (P3-a acceptance).

Verifies:
  - GitWorktreeProvider satisfies the WorkspaceProvider Protocol.
  - ProviderRegistry selects the correct provider by isolation level.
  - exec_command rejects non-argv input (shell interpolation prevention).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from micro_eval.engine.providers import (
    CommandResult,
    GitWorktreeProvider,
    IsolationLevel,
    ProviderRegistry,
    WorkspaceHandle,
    WorkspaceProvider,
)
from micro_eval.engine.providers.git_worktree import WorkspaceProviderError
from micro_eval.models.task import WorkspaceSpec, WorkspaceType


def _make_git_repo(path: Path) -> Path:
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


class TestGitWorktreeProviderProtocol:
    """GitWorktreeProvider must satisfy the WorkspaceProvider Protocol."""

    def test_isinstance_check(self, tmp_path: Path) -> None:
        provider = GitWorktreeProvider(tmp_path)
        assert isinstance(provider, WorkspaceProvider)

    def test_name_is_git_worktree(self, tmp_path: Path) -> None:
        provider = GitWorktreeProvider(tmp_path)
        assert provider.name == "git_worktree"

    def test_supported_levels_contains_logical(self, tmp_path: Path) -> None:
        provider = GitWorktreeProvider(tmp_path)
        assert IsolationLevel.logical in provider.supported_levels

    def test_create_returns_workspace_handle(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="test-cell", run_id="test-run")
        assert isinstance(handle, WorkspaceHandle)
        assert handle.workspace_path.exists()
        assert handle.provider_name == "git_worktree"
        assert handle.isolation_level == IsolationLevel.logical
        provider.cleanup(handle)

    def test_create_blank_workspace(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.blank)
        handle = provider.create(spec, cell_id="blank-cell", run_id="test-run")
        assert handle.workspace_path.exists()
        assert handle.source_repo is None
        provider.cleanup(handle)

    def test_setup_resolves_python_placeholder(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(
            type=WorkspaceType.blank,
            setup=[["{python}", "-c", "from pathlib import Path; Path('setup.txt').write_text('ok')"]],
        )

        handle = provider.create(spec, cell_id="setup-cell", run_id="test-run")

        assert (handle.workspace_path / "setup.txt").read_text() == "ok"
        provider.cleanup(handle)

    def test_collect_diff_returns_none_for_clean_worktree(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="diff-cell", run_id="test-run")
        diff = provider.collect_diff(handle)
        assert diff is None
        provider.cleanup(handle)

    def test_snapshot_returns_commit_hash(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="snap-cell", run_id="test-run")
        snap = provider.snapshot(handle)
        assert len(snap) == 40
        provider.cleanup(handle)


class TestProviderRegistry:
    """ProviderRegistry must select providers by isolation level."""

    def test_select_registered_level(self, tmp_path: Path) -> None:
        registry = ProviderRegistry()
        provider = GitWorktreeProvider(tmp_path)
        registry.register(provider)
        assert registry.select(IsolationLevel.logical) is provider

    def test_select_unregistered_level_returns_none(self, tmp_path: Path) -> None:
        registry = ProviderRegistry()
        provider = GitWorktreeProvider(tmp_path)
        registry.register(provider)
        assert registry.select(IsolationLevel.container) is None

    def test_providers_list(self, tmp_path: Path) -> None:
        registry = ProviderRegistry()
        provider = GitWorktreeProvider(tmp_path)
        registry.register(provider)
        assert len(registry.providers) == 1
        assert registry.providers[0] is provider


class TestExecCommandArgvOnly:
    """exec_command must reject non-argv inputs (security: no shell interpolation)."""

    def test_empty_argv_raises(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="argv-cell", run_id="test-run")
        with pytest.raises(ValueError, match="non-empty argv"):
            provider.exec_command(handle, [])
        provider.cleanup(handle)

    def test_argv_with_empty_string_raises(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="argv-cell2", run_id="test-run")
        with pytest.raises(ValueError, match="non-empty argv"):
            provider.exec_command(handle, ["echo", ""])
        provider.cleanup(handle)

    def test_valid_argv_executes(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="argv-cell3", run_id="test-run")
        result = provider.exec_command(handle, ["echo", "hello"])
        assert isinstance(result, CommandResult)
        assert result.exit_code == 0
        assert "hello" in result.stdout
        provider.cleanup(handle)

    def test_timeout_returns_timed_out(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = GitWorktreeProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="timeout-cell", run_id="test-run")
        result = provider.exec_command(handle, ["sleep", "10"], timeout_s=0.1)
        assert result.timed_out is True
        assert result.exit_code == -1
        provider.cleanup(handle)


class TestWorkspaceManagerProviderIntegration:
    """WorkspaceManager must use the provider registry correctly."""

    def test_prepare_uses_git_worktree_provider(self, tmp_path: Path) -> None:
        from micro_eval.engine.workspace import WorkspaceManager

        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="test-run")
        prepared = mgr.prepare(
            cell_id="int-cell",
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
        )
        assert prepared.handle is not None
        assert prepared.handle.provider_name == "git_worktree"
        mgr.cleanup()

    def test_unavailable_isolation_level_raises(self, tmp_path: Path) -> None:
        from micro_eval.engine.workspace import WorkspaceError, WorkspaceManager

        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="test-run")
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            isolation_level="container",
        )
        with pytest.raises(WorkspaceError, match="No provider available"):
            mgr.prepare(cell_id="no-provider", workspace=spec)
