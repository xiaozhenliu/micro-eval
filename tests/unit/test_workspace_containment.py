"""Containment-guard tests for WorkspaceManager._resolve_source_path
and build_same_start_snapshot.

Acceptance criteria (issue #10):
  - A git_repo workspace source path outside the project root is rejected.
  - In-project workspace paths (including the default project_root itself) continue to work.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from micro_eval.engine.workspace import WorkspaceError, WorkspaceManager, build_same_start_snapshot
from micro_eval.models.task import TaskSpec, WorkspaceSpec, WorkspaceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(path: Path) -> Path:
    """Initialise a minimal git repo at *path* with one commit."""
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


# ---------------------------------------------------------------------------
# _resolve_source_path – containment guard
# ---------------------------------------------------------------------------


class TestResolveSourcePathContainment:
    def test_default_none_path_uses_project_root_and_passes(self, tmp_path: Path) -> None:
        """Default (path=None) resolves to project_root; must not raise."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="test-run")
        resolved = mgr._resolve_source_path(None)
        assert resolved == repo

    def test_explicit_project_root_passes(self, tmp_path: Path) -> None:
        """Explicit path equal to project_root must be accepted."""
        repo = _make_git_repo(tmp_path / "project")
        mgr = WorkspaceManager(repo, run_id="test-run")
        resolved = mgr._resolve_source_path(str(repo))
        assert resolved == repo

    def test_subdirectory_inside_project_root_passes(self, tmp_path: Path) -> None:
        """A git repo nested inside project_root must be accepted."""
        project = tmp_path / "project"
        project.mkdir()
        # The outer project dir just needs to exist; the inner sub-repo is the workspace.
        subrepo = _make_git_repo(project / "subrepo")
        # Use project as project_root; subrepo is inside it.
        mgr = WorkspaceManager(project, run_id="test-run")
        resolved = mgr._resolve_source_path(str(subrepo))
        assert resolved == subrepo

    def test_absolute_path_outside_project_root_is_rejected(self, tmp_path: Path) -> None:
        """An absolute path that resolves outside project_root must raise WorkspaceError."""
        project = tmp_path / "project"
        project.mkdir()
        outside_repo = _make_git_repo(tmp_path / "outside")
        mgr = WorkspaceManager(project, run_id="test-run")
        with pytest.raises(WorkspaceError, match="escapes the project root"):
            mgr._resolve_source_path(str(outside_repo))

    def test_relative_traversal_outside_project_root_is_rejected(self, tmp_path: Path) -> None:
        """A relative path using ../ that lands outside project_root must raise WorkspaceError."""
        project = tmp_path / "project"
        project.mkdir()
        # ../outside from project resolves to tmp_path / "outside"
        outside_repo = _make_git_repo(tmp_path / "outside")
        mgr = WorkspaceManager(project, run_id="test-run")
        with pytest.raises(WorkspaceError, match="escapes the project root"):
            mgr._resolve_source_path("../outside")

    def test_tmp_path_outside_project_root_is_rejected(self, tmp_path: Path) -> None:
        """A path directly under /tmp (not under project_root) must raise WorkspaceError."""
        project = tmp_path / "project"
        project.mkdir()
        # Use a sibling of project as the outside repo.
        outside_repo = _make_git_repo(tmp_path / "sibling")
        mgr = WorkspaceManager(project, run_id="test-run")
        with pytest.raises(WorkspaceError, match="escapes the project root"):
            mgr._resolve_source_path(str(outside_repo))


# ---------------------------------------------------------------------------
# build_same_start_snapshot – containment guard produces a caveat, not a crash
# ---------------------------------------------------------------------------


class TestBuildSameStartSnapshotContainment:
    def _minimal_kwargs(self, *, project_root: Path, tasks: list[TaskSpec]) -> dict:
        return dict(
            project_root=project_root,
            tasks=tasks,
            config_hash="abc123",
            configuration_digests={"cfg": "d"},
            task_revisions={"t1": "r"},
            python_version="3.11.0",
            guardrails_digest="g",
            timestamp="2026-06-14T00:00:00+00:00",
        )

    def test_in_project_source_records_commit_no_caveat(self, tmp_path: Path) -> None:
        """An in-project git_repo workspace records a commit and adds no containment caveat."""
        repo = _make_git_repo(tmp_path / "project")
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
        )
        snapshot = build_same_start_snapshot(**self._minimal_kwargs(project_root=repo, tasks=[task]))
        assert snapshot.git_commit is not None
        assert not any("escapes" in c for c in snapshot.caveats)

    def test_outside_source_adds_caveat_and_does_not_crash(self, tmp_path: Path) -> None:
        """An out-of-project git_repo workspace path is added as a caveat rather than crashing."""
        project = tmp_path / "project"
        project.mkdir()
        outside_repo = _make_git_repo(tmp_path / "outside")
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(outside_repo)),
        )
        snapshot = build_same_start_snapshot(**self._minimal_kwargs(project_root=project, tasks=[task]))
        # Containment violation becomes a caveat (degraded, not a crash).
        assert any("escapes the project root" in c for c in snapshot.caveats)
        # Commit is None because resolution was rejected.
        assert snapshot.git_commit is None

    def test_default_none_path_works_when_project_root_is_git_repo(self, tmp_path: Path) -> None:
        """Default (path=None) resolves to project_root; must produce commit, no caveat."""
        repo = _make_git_repo(tmp_path / "project")
        task = TaskSpec(
            id="t1",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo),
        )
        snapshot = build_same_start_snapshot(**self._minimal_kwargs(project_root=repo, tasks=[task]))
        assert snapshot.git_commit is not None
        assert not any("escapes" in c for c in snapshot.caveats)

    def test_outside_caveat_is_tagged_with_task_id(self, tmp_path: Path) -> None:
        """The fail-soft caveat must identify which task's workspace was rejected."""
        project = tmp_path / "project"
        project.mkdir()
        outside_repo = _make_git_repo(tmp_path / "outside")
        task = TaskSpec(
            id="t-tagged",
            name="Task",
            input_payload="",
            workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(outside_repo)),
        )
        snapshot = build_same_start_snapshot(**self._minimal_kwargs(project_root=project, tasks=[task]))
        assert any("[task=t-tagged]" in c for c in snapshot.caveats)


# ---------------------------------------------------------------------------
# _copy_files – containment guard (issue #10, `files` workspace entry point)
# ---------------------------------------------------------------------------


class TestCopyFilesContainment:
    def test_in_project_file_source_is_copied(self, tmp_path: Path) -> None:
        """A `files` source inside the project root must be copied without error."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "data.txt").write_text("payload")
        mgr = WorkspaceManager(project, run_id="test-run")
        dest = project / ".micro-eval" / "dest"
        dest.mkdir(parents=True)
        spec = WorkspaceSpec(type=WorkspaceType.files, files=["data.txt"])
        mgr._copy_files(spec, dest)
        assert (dest / "data.txt").read_text() == "payload"

    def test_absolute_file_source_outside_project_root_is_rejected(self, tmp_path: Path) -> None:
        """An absolute `files` source outside the project root must raise WorkspaceError."""
        project = tmp_path / "project"
        project.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("top secret")
        mgr = WorkspaceManager(project, run_id="test-run")
        dest = project / ".micro-eval" / "dest"
        dest.mkdir(parents=True)
        spec = WorkspaceSpec(type=WorkspaceType.files, files=[str(secret)])
        with pytest.raises(WorkspaceError, match="escapes the project root"):
            mgr._copy_files(spec, dest)

    def test_relative_traversal_file_source_is_rejected(self, tmp_path: Path) -> None:
        """A `files` source using ../ to escape the project root must raise WorkspaceError."""
        project = tmp_path / "project"
        project.mkdir()
        (tmp_path / "secret.txt").write_text("top secret")
        mgr = WorkspaceManager(project, run_id="test-run")
        dest = project / ".micro-eval" / "dest"
        dest.mkdir(parents=True)
        spec = WorkspaceSpec(type=WorkspaceType.files, files=["../secret.txt"])
        with pytest.raises(WorkspaceError, match="escapes the project root"):
            mgr._copy_files(spec, dest)
