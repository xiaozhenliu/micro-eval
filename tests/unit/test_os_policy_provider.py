"""OS policy provider tests (P3-b acceptance).

Verifies:
  - SeatbeltProvider satisfies the WorkspaceProvider Protocol on macOS.
  - BubblewrapProvider satisfies the WorkspaceProvider Protocol on Linux.
  - Platform-unavailable provider has empty supported_levels.
  - Degradation from os_policy to logical when provider is unavailable.
  - Seatbelt restricts workspace-external writes (negative test, macOS only).
  - exec_command argv-only validation.
  - Seatbelt profile generation for all network policies.
  - Bubblewrap argv construction with bind-mount flags.
  - exec_command timeout handling for both providers.
  - Delegation methods (collect_artifacts, collect_diff, snapshot, restore, cleanup).
  - Tool unavailable (shutil.which returns None) causes empty supported_levels.
  - Platform detection routes to correct provider.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from micro_eval.engine.providers import (
    IsolationLevel,
    WorkspaceProvider,
)
from micro_eval.engine.providers.base import CommandResult, ExecutionRequest, WorkspaceHandle
from micro_eval.engine.providers.os_policy import (
    BubblewrapProvider,
    SeatbeltProvider,
    _build_bwrap_argv,
    _build_seatbelt_profile,
)
from micro_eval.engine.providers.git_worktree import WorkspaceProviderError
from micro_eval.engine.workspace import WorkspaceManager
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


class TestSeatbeltProviderProtocol:
    def test_isinstance_check(self, tmp_path: Path) -> None:
        provider = SeatbeltProvider(tmp_path)
        assert isinstance(provider, WorkspaceProvider)

    def test_name(self, tmp_path: Path) -> None:
        assert SeatbeltProvider(tmp_path).name == "seatbelt"

    @pytest.mark.skipif(
        platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
        reason="Seatbelt only available on macOS",
    )
    def test_supported_levels_on_macos(self, tmp_path: Path) -> None:
        provider = SeatbeltProvider(tmp_path)
        assert IsolationLevel.os_policy in provider.supported_levels

    def test_supported_levels_empty_on_wrong_platform(self, tmp_path: Path) -> None:
        with patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Linux"):
            provider = SeatbeltProvider(tmp_path)
            assert provider.supported_levels == []


class TestBubblewrapProviderProtocol:
    def test_isinstance_check(self, tmp_path: Path) -> None:
        provider = BubblewrapProvider(tmp_path)
        assert isinstance(provider, WorkspaceProvider)

    def test_name(self, tmp_path: Path) -> None:
        assert BubblewrapProvider(tmp_path).name == "bubblewrap"

    def test_supported_levels_empty_on_wrong_platform(self, tmp_path: Path) -> None:
        with patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Darwin"):
            provider = BubblewrapProvider(tmp_path)
            assert provider.supported_levels == []


class TestSeatbeltProfile:
    def test_profile_contains_workspace_path(self, tmp_path: Path) -> None:
        profile = _build_seatbelt_profile(tmp_path, "full")
        assert str(tmp_path) in profile

    def test_profile_network_none_denies(self, tmp_path: Path) -> None:
        profile = _build_seatbelt_profile(tmp_path, "none")
        assert "(deny network*)" in profile

    def test_profile_network_full_allows(self, tmp_path: Path) -> None:
        profile = _build_seatbelt_profile(tmp_path, "full")
        assert "(allow network*)" in profile


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="Seatbelt only available on macOS",
)
class TestSeatbeltExecution:
    def test_command_executes_in_workspace(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = SeatbeltProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="seatbelt-cell", run_id="test-run")
        result = provider.exec_command(handle, ["cat", "file.txt"])
        assert result.exit_code == 0
        assert "content" in result.stdout
        provider.cleanup(handle)

    def test_workspace_external_write_is_rejected(self, tmp_path: Path) -> None:
        """Seatbelt should prevent writing outside the workspace."""
        repo = _make_git_repo(tmp_path / "project")
        outside = tmp_path / "outside.txt"
        provider = SeatbeltProvider(repo)
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            network_policy="none",
        )
        handle = provider.create(spec, cell_id="seatbelt-deny", run_id="test-run")
        result = provider.exec_command(
            handle,
            ["/bin/sh", "-c", f"echo hacked > {outside}"],
        )
        assert not outside.exists() or result.exit_code != 0
        provider.cleanup(handle)

    def test_argv_validation(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = SeatbeltProvider(repo)
        spec = WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo))
        handle = provider.create(spec, cell_id="seatbelt-argv", run_id="test-run")
        with pytest.raises(ValueError, match="non-empty argv"):
            provider.exec_command(handle, [])
        provider.cleanup(handle)


class TestOsPolicyDegradation:
    def test_os_policy_degrades_to_logical_with_caveat(self, tmp_path: Path) -> None:
        """When os_policy provider is unavailable, prepare should degrade to logical."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="degrade-run")
        # Remove any os_policy providers from registry
        mgr._registry._providers = [
            p for p in mgr._registry._providers
            if IsolationLevel.os_policy not in p.supported_levels
        ]
        caveats: list[str] = []
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            isolation_level="os_policy",
        )
        prepared = mgr.prepare(cell_id="degrade-cell", workspace=spec, caveats=caveats)
        assert prepared.path.exists()
        assert any("os_policy unavailable" in c for c in caveats)
        mgr.cleanup()

    def test_container_level_does_not_degrade(self, tmp_path: Path) -> None:
        """Container/VM levels must fail hard, not degrade to local."""
        from micro_eval.engine.workspace import WorkspaceError

        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="no-degrade-run")
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            isolation_level="container",
        )
        with pytest.raises(WorkspaceError, match="No provider available"):
            mgr.prepare(cell_id="no-degrade-cell", workspace=spec)


# ---------------------------------------------------------------------------
# New tests for increased coverage
# ---------------------------------------------------------------------------


class TestSeatbeltProfileAllNetworkPolicies:
    """_build_seatbelt_profile covers all three network policy branches."""

    def test_allowlist_network_policy(self, tmp_path: Path) -> None:
        with pytest.raises(WorkspaceProviderError, match="allowlist requires explicit rules"):
            _build_seatbelt_profile(tmp_path, "allowlist")

    def test_full_network_allows_all(self, tmp_path: Path) -> None:
        profile = _build_seatbelt_profile(tmp_path, "full")
        assert "(allow network*)" in profile
        assert "(deny network*)" not in profile

    def test_none_network_denies_all(self, tmp_path: Path) -> None:
        profile = _build_seatbelt_profile(tmp_path, "none")
        assert "(deny network*)" in profile
        assert "(allow network*)" not in profile

    def test_profile_has_version_and_deny_default(self, tmp_path: Path) -> None:
        profile = _build_seatbelt_profile(tmp_path, "full")
        assert "(version 1)" in profile
        assert "(deny default)" in profile

    def test_profile_restricts_writes_to_subpath(self, tmp_path: Path) -> None:
        profile = _build_seatbelt_profile(tmp_path, "full")
        ws = str(tmp_path)
        assert f'(allow file-write* (subpath "{ws}"))' in profile

    def test_profile_escapes_double_quote_in_path(self, tmp_path: Path) -> None:
        # Simulate a path containing a double-quote in its string representation
        # by testing the escape logic directly (we patch str() output via a mock path).
        from unittest.mock import MagicMock
        fake_path = MagicMock(spec=Path)
        fake_path.__str__ = MagicMock(return_value='/tmp/a"b')
        profile = _build_seatbelt_profile(fake_path, "full")
        # The quote must be escaped in the profile
        assert '\\"' in profile
        assert '/tmp/a"b' not in profile


class TestBuildBwrapArgv:
    """_build_bwrap_argv constructs correct bwrap command line."""

    def test_starts_with_bwrap(self, tmp_path: Path) -> None:
        argv = _build_bwrap_argv(tmp_path, "full", ["echo", "hi"])
        assert argv[0] == "bwrap"

    def test_bind_mounts_workspace_rw(self, tmp_path: Path) -> None:
        ws = str(tmp_path)
        argv = _build_bwrap_argv(tmp_path, "full", ["echo"])
        # workspace should be bound read-write with --bind
        bind_idx = argv.index("--bind")
        assert argv[bind_idx + 1] == ws
        assert argv[bind_idx + 2] == ws

    def test_ro_bind_system_dirs(self, tmp_path: Path) -> None:
        argv = _build_bwrap_argv(tmp_path, "full", ["echo"])
        ro_binds = [argv[i + 1] for i, a in enumerate(argv) if a == "--ro-bind"]
        assert "/usr" in ro_binds
        assert "/bin" in ro_binds
        assert "/etc" in ro_binds

    def test_proc_dev_tmpfs_present(self, tmp_path: Path) -> None:
        argv = _build_bwrap_argv(tmp_path, "full", ["echo"])
        assert "--proc" in argv
        assert "--unshare-pid" in argv
        assert "--die-with-parent" in argv
        assert "--dev" in argv
        assert "--tmpfs" in argv

    def test_chdir_to_workspace(self, tmp_path: Path) -> None:
        ws = str(tmp_path)
        argv = _build_bwrap_argv(tmp_path, "full", ["echo"])
        chdir_idx = argv.index("--chdir")
        assert argv[chdir_idx + 1] == ws

    def test_requested_cwd_does_not_change_workspace_mount(self, tmp_path: Path) -> None:
        cwd = tmp_path / "nested"
        argv = _build_bwrap_argv(tmp_path, "full", ["pwd"], cwd=cwd)
        assert argv[argv.index("--chdir") + 1] == str(cwd)
        assert argv[argv.index("--bind") + 1] == str(tmp_path)

    def test_python_prefix_and_project_are_readonly_before_workspace(self, tmp_path: Path) -> None:
        import sys

        argv = _build_bwrap_argv(tmp_path / "workspace", "full", ["python"], project_root=tmp_path)
        mounts = [argv[i + 1] for i, item in enumerate(argv) if item == "--ro-bind"]
        assert str(Path(sys.prefix).absolute()) in mounts
        assert str(Path(sys.executable).resolve().parent.parent) in mounts
        assert str(tmp_path) in mounts
        assert "/" not in mounts
        assert all(i < argv.index("--bind") for i, item in enumerate(argv) if item == "--ro-bind")

    def test_inner_argv_appended_at_end(self, tmp_path: Path) -> None:
        inner = ["python3", "-c", "print('hi')"]
        argv = _build_bwrap_argv(tmp_path, "full", inner)
        assert argv[-len(inner):] == inner

    def test_network_none_adds_unshare_net(self, tmp_path: Path) -> None:
        argv = _build_bwrap_argv(tmp_path, "none", ["echo"])
        assert "--unshare-net" in argv

    def test_network_allowlist_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(WorkspaceProviderError, match="allowlist requires explicit rules"):
            _build_bwrap_argv(tmp_path, "allowlist", ["echo"])

    def test_network_full_no_unshare_net(self, tmp_path: Path) -> None:
        argv = _build_bwrap_argv(tmp_path, "full", ["echo"])
        assert "--unshare-net" not in argv


class TestSeatbeltProviderToolAvailability:
    """SeatbeltProvider._available reflects tool presence."""

    def test_unavailable_when_sandbox_exec_not_found(self, tmp_path: Path) -> None:
        with (
            patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Darwin"),
            patch("micro_eval.engine.providers.os_policy.shutil.which", return_value=None),
        ):
            provider = SeatbeltProvider(tmp_path)
            assert provider.supported_levels == []
            assert provider._available is False

    def test_available_when_on_darwin_with_tool(self, tmp_path: Path) -> None:
        with (
            patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Darwin"),
            patch("micro_eval.engine.providers.os_policy.shutil.which", return_value="/usr/bin/sandbox-exec"),
        ):
            provider = SeatbeltProvider(tmp_path)
            assert provider._available is True
            assert IsolationLevel.os_policy in provider.supported_levels

    def test_unavailable_on_linux(self, tmp_path: Path) -> None:
        with patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Linux"):
            provider = SeatbeltProvider(tmp_path)
            assert provider._available is False

    def test_unavailable_on_windows(self, tmp_path: Path) -> None:
        with patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Windows"):
            provider = SeatbeltProvider(tmp_path)
            assert provider._available is False


class TestBubblewrapProviderToolAvailability:
    """BubblewrapProvider._available reflects tool presence."""

    def test_unavailable_when_bwrap_not_found(self, tmp_path: Path) -> None:
        with (
            patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Linux"),
            patch("micro_eval.engine.providers.os_policy.shutil.which", return_value=None),
        ):
            provider = BubblewrapProvider(tmp_path)
            assert provider.supported_levels == []
            assert provider._available is False

    def test_available_when_on_linux_with_tool(self, tmp_path: Path) -> None:
        with (
            patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Linux"),
            patch("micro_eval.engine.providers.os_policy.shutil.which", return_value="/usr/bin/bwrap"),
        ):
            provider = BubblewrapProvider(tmp_path)
            assert provider._available is True
            assert IsolationLevel.os_policy in provider.supported_levels

    def test_unavailable_on_darwin(self, tmp_path: Path) -> None:
        with patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Darwin"):
            provider = BubblewrapProvider(tmp_path)
            assert provider._available is False

    def test_unavailable_on_windows(self, tmp_path: Path) -> None:
        with patch("micro_eval.engine.providers.os_policy.platform.system", return_value="Windows"):
            provider = BubblewrapProvider(tmp_path)
            assert provider._available is False


@pytest.mark.parametrize("provider_cls,executable", [
    (SeatbeltProvider, "sandbox-exec"), (BubblewrapProvider, "bwrap"),
])
class TestOsExecution:
    def _handle(self, path: Path, policy: str = "full") -> WorkspaceHandle:
        return WorkspaceHandle(path, "test", IsolationLevel.os_policy,
                               metadata={"network_policy": policy})

    async def test_request_and_bounded_result_preserved(self, tmp_path, provider_cls, executable):
        provider = provider_cls(tmp_path)
        request = ExecutionRequest(
            argv=["echo", "hello"], cwd=tmp_path, env={"FOO": "bar"}, stdin=b"input",
            timeout_s=1.0, output_cap_bytes=123,
        )
        expected = CommandResult(0, "bounded", "error", stdout_truncated=True)
        with patch("micro_eval.engine.providers.os_policy.run_process", new_callable=AsyncMock,
                   return_value=expected) as runner:
            result = await provider.execute(self._handle(tmp_path), request)
        assert result is expected
        actual = runner.call_args.args[0]
        assert actual.argv[0] == executable
        assert actual.argv[-2:] == ["echo", "hello"]
        assert actual.cwd == tmp_path
        assert actual.env == request.env
        assert actual.stdin == request.stdin
        assert actual.timeout_s == 1.0
        assert actual.output_cap_bytes == 123

    def test_sync_compatibility_uses_same_runner(self, tmp_path, provider_cls, executable):
        expected = CommandResult(-1, "partial", timed_out=True)
        with patch("micro_eval.engine.providers.os_policy.run_process", new_callable=AsyncMock,
                   return_value=expected) as runner:
            result = provider_cls(tmp_path).exec_command(
                self._handle(tmp_path), ["sleep", "10"], timeout_s=0.1,
            )
        assert result is expected
        assert runner.call_args.args[0].argv[0] == executable
        assert runner.call_args.args[0].timeout_s == 0.1

    def test_sync_default_env_excludes_unrelated_secrets(self, tmp_path, provider_cls, executable, monkeypatch):
        monkeypatch.setenv("PRIVATE_ACCOUNT_TOKEN", "do-not-inherit")
        with patch("micro_eval.engine.providers.os_policy.run_process", new_callable=AsyncMock,
                   return_value=CommandResult(0)) as runner:
            provider_cls(tmp_path).exec_command(self._handle(tmp_path), ["env"])
        assert "PRIVATE_ACCOUNT_TOKEN" not in runner.call_args.args[0].env

    @pytest.mark.parametrize("argv", [[], ["echo", ""]])
    async def test_invalid_argv_rejected(self, tmp_path, provider_cls, executable, argv):
        with pytest.raises(ValueError, match="non-empty argv"):
            await provider_cls(tmp_path).execute(self._handle(tmp_path), ExecutionRequest(argv))

    async def test_network_none_wrapped(self, tmp_path, provider_cls, executable):
        with patch("micro_eval.engine.providers.os_policy.run_process", new_callable=AsyncMock,
                   return_value=CommandResult(0)) as runner:
            await provider_cls(tmp_path).execute(
                self._handle(tmp_path, "none"), ExecutionRequest(["echo"]),
            )
        argv = runner.call_args.args[0].argv
        assert "(deny network*)" in argv[2] if executable == "sandbox-exec" else "--unshare-net" in argv

    async def test_only_exact_output_sibling_is_writable(self, tmp_path, provider_cls, executable):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        output = tmp_path / ".micro-eval-io-one"
        output.mkdir()
        handle = self._handle(workspace)
        handle.metadata["output_path"] = str(output)
        with patch("micro_eval.engine.providers.os_policy.run_process", new_callable=AsyncMock,
                   return_value=CommandResult(0)) as runner:
            await provider_cls(tmp_path).execute(handle, ExecutionRequest(["echo"]))
        argv = runner.call_args.args[0].argv
        if executable == "sandbox-exec":
            assert f'(subpath "{output}")' in argv[2]
            assert f'(subpath "{tmp_path}")' not in argv[2]
        else:
            writable = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--bind"]
            assert writable == [str(workspace), str(output)]

    async def test_run_root_cannot_be_claimed_as_output(self, tmp_path, provider_cls, executable):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        handle = self._handle(workspace)
        handle.metadata["output_path"] = str(tmp_path)
        with pytest.raises(WorkspaceProviderError, match="dedicated workspace sibling"):
            await provider_cls(tmp_path).execute(handle, ExecutionRequest(["echo"]))

    def test_create_setup_uses_policy_and_rolls_back_on_exception(self, tmp_path, provider_cls, executable):
        provider = provider_cls(tmp_path)
        with patch.object(provider._inner, "_run_setup", side_effect=AssertionError("host setup")):
            with patch.object(provider, "execute", new_callable=AsyncMock,
                              side_effect=RuntimeError("start failed")):
                with pytest.raises(RuntimeError, match="start failed"):
                    provider.create(WorkspaceSpec(setup=[["echo", "setup"]]), cell_id="setup", run_id="rollback")
        assert not (tmp_path / ".micro-eval/workspaces/rollback/setup").exists()

    def test_setup_failure_is_recorded_and_stops_later_steps(self, tmp_path, provider_cls, executable):
        provider = provider_cls(tmp_path)
        with patch.object(provider._inner, "_run_setup", side_effect=AssertionError("host setup")):
            with patch.object(provider, "execute", new_callable=AsyncMock,
                              return_value=CommandResult(7)) as execute:
                handle = provider.create(WorkspaceSpec(setup=[["false"], ["echo", "unreachable"]]),
                                         cell_id="setup", run_id="failure")
        assert handle.setup_exit_code == 7
        assert execute.await_count == 1
        assert handle.metadata["network_policy_requested"] == "full"
        assert handle.metadata["network_policy_effective"] == "full"
        provider.cleanup(handle)

    def test_allowlist_rejected_before_materialization(self, tmp_path, provider_cls, executable):
        provider = provider_cls(tmp_path)
        with patch.object(provider._inner, "create") as create:
            with pytest.raises(WorkspaceProviderError, match="allowlist requires explicit rules"):
                provider.create(WorkspaceSpec(network_policy="allowlist"), cell_id="x", run_id="x")
        create.assert_not_called()


class TestSeatbeltDelegationMethods:
    """SeatbeltProvider delegates collect_artifacts, collect_diff, snapshot, cleanup to inner."""

    def _make_handle(self, workspace_path: Path) -> WorkspaceHandle:
        return WorkspaceHandle(
            workspace_path=workspace_path,
            provider_name="seatbelt",
            isolation_level=IsolationLevel.os_policy,
            metadata={},
        )

    def test_collect_artifacts_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = SeatbeltProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "collect_artifacts", return_value=[]) as mock_ca:
            result = provider.collect_artifacts(handle)
        mock_ca.assert_called_once_with(handle)
        assert result == []

    def test_collect_diff_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = SeatbeltProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "collect_diff", return_value="diff output") as mock_cd:
            result = provider.collect_diff(handle)
        mock_cd.assert_called_once_with(handle)
        assert result == "diff output"

    def test_snapshot_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = SeatbeltProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "snapshot", return_value="snap123") as mock_snap:
            result = provider.snapshot(handle)
        mock_snap.assert_called_once_with(handle)
        assert result == "snap123"

    def test_restore_raises_not_implemented(self, tmp_path: Path) -> None:
        provider = SeatbeltProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with pytest.raises(NotImplementedError, match="restore not supported"):
            provider.restore(handle, "snap123")

    def test_cleanup_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = SeatbeltProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "cleanup") as mock_cleanup:
            provider.cleanup(handle)
        mock_cleanup.assert_called_once_with(handle)


class TestBubblewrapDelegationMethods:
    """BubblewrapProvider delegates collect_artifacts, collect_diff, snapshot, cleanup to inner."""

    def _make_handle(self, workspace_path: Path) -> WorkspaceHandle:
        return WorkspaceHandle(
            workspace_path=workspace_path,
            provider_name="bubblewrap",
            isolation_level=IsolationLevel.os_policy,
            metadata={},
        )

    def test_collect_artifacts_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = BubblewrapProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "collect_artifacts", return_value=[]) as mock_ca:
            result = provider.collect_artifacts(handle)
        mock_ca.assert_called_once_with(handle)
        assert result == []

    def test_collect_diff_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = BubblewrapProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "collect_diff", return_value=None) as mock_cd:
            result = provider.collect_diff(handle)
        mock_cd.assert_called_once_with(handle)
        assert result is None

    def test_snapshot_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = BubblewrapProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "snapshot", return_value="bwrap-snap") as mock_snap:
            result = provider.snapshot(handle)
        mock_snap.assert_called_once_with(handle)
        assert result == "bwrap-snap"

    def test_restore_raises_not_implemented(self, tmp_path: Path) -> None:
        provider = BubblewrapProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with pytest.raises(NotImplementedError, match="restore not supported"):
            provider.restore(handle, "bwrap-snap")

    def test_cleanup_delegates_to_inner(self, tmp_path: Path) -> None:
        provider = BubblewrapProvider(tmp_path)
        handle = self._make_handle(tmp_path)
        with patch.object(provider._inner, "cleanup") as mock_cleanup:
            provider.cleanup(handle)
        mock_cleanup.assert_called_once_with(handle)


class TestBubblewrapCreateMethod:
    """BubblewrapProvider.create builds WorkspaceHandle with correct metadata."""

    def test_create_sets_sandbox_type_and_network_policy(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = BubblewrapProvider(repo)
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
        )
        handle = provider.create(spec, cell_id="bwrap-create", run_id="test-run")
        assert handle.provider_name == "bubblewrap"
        assert handle.isolation_level == IsolationLevel.os_policy
        assert handle.metadata["sandbox_type"] == "bubblewrap"
        assert "network_policy" in handle.metadata
        provider.cleanup(handle)

    def test_create_with_network_policy_none(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project2")
        provider = BubblewrapProvider(repo)
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            network_policy="none",
        )
        handle = provider.create(spec, cell_id="bwrap-net-none", run_id="test-run")
        assert handle.metadata["network_policy"] == "none"
        provider.cleanup(handle)


class TestSeatbeltCreateMethod:
    """SeatbeltProvider.create builds WorkspaceHandle with correct metadata."""

    def test_create_sets_sandbox_type_and_network_policy(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        provider = SeatbeltProvider(repo)
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
        )
        handle = provider.create(spec, cell_id="sb-create", run_id="test-run")
        assert handle.provider_name == "seatbelt"
        assert handle.isolation_level == IsolationLevel.os_policy
        assert handle.metadata["sandbox_type"] == "seatbelt"
        assert "network_policy" in handle.metadata
        provider.cleanup(handle)

    def test_create_network_policy_stored_in_metadata(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project2")
        provider = SeatbeltProvider(repo)
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            network_policy="none",
        )
        handle = provider.create(spec, cell_id="sb-net-none", run_id="test-run")
        assert handle.metadata["network_policy"] == "none"
        provider.cleanup(handle)
