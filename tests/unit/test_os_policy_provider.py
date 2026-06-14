"""OS policy provider tests (P3-b acceptance).

Verifies:
  - SeatbeltProvider satisfies the WorkspaceProvider Protocol on macOS.
  - BubblewrapProvider satisfies the WorkspaceProvider Protocol on Linux.
  - Platform-unavailable provider has empty supported_levels.
  - Degradation from os_policy to logical when provider is unavailable.
  - Seatbelt restricts workspace-external writes (negative test, macOS only).
  - exec_command argv-only validation.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from micro_eval.engine.providers import (
    IsolationLevel,
    WorkspaceProvider,
)
from micro_eval.engine.providers.os_policy import (
    BubblewrapProvider,
    SeatbeltProvider,
    _build_seatbelt_profile,
)
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
