"""Workspace resolver and archive guards (round-6 review, 2026-09-12).

- a workspace directory that is a symlink (even to a sibling workspace) is
  not resolvable, and a workspace.json whose id differs is refused;
- archiving and deleting take the workspace lock and refuse when jobs are
  pending;
- `build-plan --strict-paths` refuses a symlinked or hard-linked eval.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from micro_eval.cli.main import app
from micro_eval.server.queue import QueueDB
from micro_eval.server.workspace import WorkspaceError, WorkspaceManager


def _manager(tmp_path: Path) -> WorkspaceManager:
    data_root = tmp_path / "data"
    data_root.mkdir()
    return WorkspaceManager(data_root)


def test_symlinked_workspace_dir_is_not_resolvable(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    real = manager.create(name="a", owner="alice")
    alias_id = "ws-20260912T000000Z-deadbeef"
    (manager.workspaces_dir / alias_id).symlink_to(manager.workspaces_dir / real.workspace_id)

    assert manager.resolve_path(real.workspace_id) is not None
    assert manager.resolve_path(alias_id) is None
    assert manager.get(alias_id) is None


def test_workspace_json_id_mismatch_is_refused(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    other_id = "ws-20260912T000000Z-cafebabe"
    (manager.workspaces_dir / other_id).mkdir()
    # Copy A's metadata (which names A's id) into B's directory.
    (manager.workspaces_dir / other_id / "workspace.json").write_text(
        (manager.workspaces_dir / ws.workspace_id / "workspace.json").read_text()
    )
    assert manager.resolve_path(other_id) is None


def test_archiving_with_pending_jobs_is_refused(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    db = QueueDB(manager.data_root / "queue.db")
    try:
        db.enqueue(workspace_id=ws.workspace_id, owner="alice", plan_json="{}")
    finally:
        db.close()

    with pytest.raises(WorkspaceError, match="pending"):
        manager.update(ws.workspace_id, status="archived")
    assert manager.get(ws.workspace_id).status == "active"


def test_archiving_without_pending_jobs_succeeds_and_lock_file_lives_in_runtime_dir(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    meta = manager.update(ws.workspace_id, status="archived")
    assert meta is not None and meta.status == "archived"
    assert (manager.workspaces_dir / ws.workspace_id / ".micro-eval" / "workspace.lock").exists()


def test_deleting_with_pending_jobs_is_refused(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    db = QueueDB(manager.data_root / "queue.db")
    try:
        db.enqueue(workspace_id=ws.workspace_id, owner="alice", plan_json="{}")
    finally:
        db.close()

    with pytest.raises(WorkspaceError, match="pending"):
        manager.delete(ws.workspace_id)
    assert manager.get(ws.workspace_id) is not None


def test_deleting_without_pending_jobs_removes_the_directory(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    assert manager.delete(ws.workspace_id) is True
    assert not (manager.workspaces_dir / ws.workspace_id).exists()
    assert manager.delete(ws.workspace_id) is False


def test_lock_refuses_symlinked_runtime_dir(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    # Round-7 review: a `.micro-eval` symlink must not redirect the lock file
    # outside the workspace (that would void the archive/enqueue exclusion).
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    ws_dir = manager.workspaces_dir / ws.workspace_id
    outside = tmp_path_factory.mktemp("outside")
    import shutil

    shutil.rmtree(ws_dir / ".micro-eval")
    (ws_dir / ".micro-eval").symlink_to(outside)

    with pytest.raises(WorkspaceError, match="plain directory"):
        with WorkspaceManager.lock(ws_dir):
            pass
    with pytest.raises(WorkspaceError, match="plain directory"):
        manager.update(ws.workspace_id, status="archived")
    assert not (outside / "workspace.lock").exists()
    assert manager.get(ws.workspace_id).status == "active"


def test_lock_refuses_runtime_dir_that_is_a_file(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    ws_dir = manager.workspaces_dir / ws.workspace_id
    import shutil

    shutil.rmtree(ws_dir / ".micro-eval")
    (ws_dir / ".micro-eval").write_text("not a dir")
    with pytest.raises(WorkspaceError, match="plain directory"):
        with WorkspaceManager.lock(ws_dir):
            pass


def test_workspace_update_cli_reports_pending_jobs_cleanly(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    ws = manager.create(name="a", owner="alice")
    db = QueueDB(manager.data_root / "queue.db")
    try:
        db.enqueue(workspace_id=ws.workspace_id, owner="alice", plan_json="{}")
    finally:
        db.close()
    result = CliRunner().invoke(
        app, ["workspace", "update", ws.workspace_id, "--status", "archived", "--data-root", str(manager.data_root)]
    )
    assert result.exit_code == 1
    assert "pending" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_build_plan_strict_refuses_linked_eval_yaml(tmp_path: Path, link: str) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    real = tmp_path / "real-eval.yaml"
    real.write_text("project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n")
    (ws / "tasks").mkdir()
    (ws / "tasks" / "t.yaml").write_text('id: t\nname: T\ninput_payload: "x"\n')
    if link == "symlink":
        (ws / "eval.yaml").symlink_to(real)
    else:
        os.link(real, ws / "eval.yaml")

    strict = CliRunner().invoke(app, ["build-plan", "--workspace", str(ws), "--strict-paths"])
    assert strict.exit_code == 1
    assert "plain file" in strict.output
