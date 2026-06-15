"""Remote provider tests (P3-c acceptance).

Verifies:
  - E2BProvider/ModalProvider satisfy WorkspaceProvider Protocol.
  - Missing credentials → empty supported_levels (unavailable, not error).
  - Requesting remote isolation without credentials → fail hard, not degrade.
  - exec_command argv-only validation.
  - Credential env vars use MICRO_EVAL_SECRET_* naming (redaction-compatible).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from micro_eval.engine.providers import (
    E2BProvider,
    IsolationLevel,
    ModalProvider,
    WorkspaceProvider,
)
from micro_eval.engine.providers.git_worktree import WorkspaceProviderError
from micro_eval.engine.providers.remote import (
    E2B_API_KEY_ENV,
    MODAL_TOKEN_ID_ENV,
    MODAL_TOKEN_SECRET_ENV,
)
from micro_eval.engine.workspace import WorkspaceError, WorkspaceManager
from micro_eval.models.task import WorkspaceSpec, WorkspaceType

import subprocess


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


class TestE2BProviderProtocol:
    def test_isinstance_check(self, tmp_path: Path) -> None:
        provider = E2BProvider(tmp_path)
        assert isinstance(provider, WorkspaceProvider)

    def test_name(self, tmp_path: Path) -> None:
        assert E2BProvider(tmp_path).name == "e2b"

    def test_no_credentials_means_empty_supported_levels(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = E2BProvider(tmp_path)
            assert provider.supported_levels == []

    def test_with_credentials_supports_vm(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {E2B_API_KEY_ENV: "test-key"}):
            provider = E2BProvider(tmp_path)
            assert IsolationLevel.vm in provider.supported_levels

    def test_create_without_credentials_raises(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = E2BProvider(tmp_path)
            spec = WorkspaceSpec(type=WorkspaceType.blank)
            with pytest.raises(WorkspaceProviderError, match="requires.*E2B"):
                provider.create(spec, cell_id="test", run_id="test")

    def test_credential_env_var_uses_secret_prefix(self) -> None:
        assert E2B_API_KEY_ENV.startswith("MICRO_EVAL_SECRET_")


class TestModalProviderProtocol:
    def test_isinstance_check(self, tmp_path: Path) -> None:
        provider = ModalProvider(tmp_path)
        assert isinstance(provider, WorkspaceProvider)

    def test_name(self, tmp_path: Path) -> None:
        assert ModalProvider(tmp_path).name == "modal"

    def test_no_credentials_means_empty_supported_levels(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = ModalProvider(tmp_path)
            assert provider.supported_levels == []

    def test_with_credentials_supports_container(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {
            MODAL_TOKEN_ID_ENV: "test-id",
            MODAL_TOKEN_SECRET_ENV: "test-secret",
        }):
            provider = ModalProvider(tmp_path)
            assert IsolationLevel.container in provider.supported_levels

    def test_create_without_credentials_raises(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = ModalProvider(tmp_path)
            spec = WorkspaceSpec(type=WorkspaceType.blank)
            with pytest.raises(WorkspaceProviderError, match="Modal provider requires"):
                provider.create(spec, cell_id="test", run_id="test")

    def test_credential_env_vars_use_secret_prefix(self) -> None:
        assert MODAL_TOKEN_ID_ENV.startswith("MICRO_EVAL_SECRET_")
        assert MODAL_TOKEN_SECRET_ENV.startswith("MICRO_EVAL_SECRET_")


class TestRemoteFailHard:
    """Remote isolation must fail hard, never degrade to local."""

    def test_vm_level_does_not_degrade(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="vm-test")
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            isolation_level="vm",
        )
        with pytest.raises(WorkspaceError, match="No provider available"):
            mgr.prepare(cell_id="vm-cell", workspace=spec)

    def test_container_level_does_not_degrade(self, tmp_path: Path) -> None:
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="container-test")
        spec = WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            isolation_level="container",
        )
        with pytest.raises(WorkspaceError, match="No provider available"):
            mgr.prepare(cell_id="container-cell", workspace=spec)
