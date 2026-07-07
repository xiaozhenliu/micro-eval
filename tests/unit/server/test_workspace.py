"""Tests for WorkspaceManager."""

import os
import re
from unittest.mock import patch

import pytest

from micro_eval.server.workspace import WorkspaceError, WorkspaceManager


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    (root / "workspaces").mkdir()
    return root


@pytest.fixture
def manager(data_root):
    return WorkspaceManager(data_root)


def test_create_blank(manager):
    meta = manager.create(name="test-ws", owner="alice")
    assert meta.workspace_id.startswith("ws-")
    assert meta.owner == "alice"
    assert meta.status == "active"
    ws_dir = manager.workspaces_dir / meta.workspace_id
    assert (ws_dir / "eval.yaml").exists()
    assert (ws_dir / "workspace.json").exists()
    assert (ws_dir / ".micro-eval" / "runs").exists()


def test_create_from_template(manager, data_root):
    tpl_dir = data_root / "templates" / "tpl-a"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "eval.yaml").write_text("project_name: tpl-a\n")
    (tpl_dir / "template.json").write_text(
        '{"schema_version":"1.0","template_id":"tpl-a","name":"A","version":"2.0.0","created_at":"","updated_at":""}'
    )
    meta = manager.create(name="from-tpl", owner="bob", template_id="tpl-a")
    assert meta.template_id == "tpl-a"
    assert meta.template_version == "2.0.0"
    ws_dir = manager.workspaces_dir / meta.workspace_id
    assert (ws_dir / "eval.yaml").read_text() == "project_name: tpl-a\n"


def test_create_template_not_found(manager):
    with pytest.raises(WorkspaceError, match="template not found"):
        manager.create(name="fail", owner="alice", template_id="no-such")
    # Template-not-found is a domain error hit before any copy happens;
    # the partially created workspace dir must not survive it.
    assert list(manager.workspaces_dir.iterdir()) == []


@pytest.mark.parametrize(
    "bad_id",
    ["..", ".", "/etc", "../../../etc/ssh", "../evil", "a/b", "x" * 65, "tpl\n"],
)
def test_create_rejects_traversal_template_id(manager, bad_id):
    """A traversal template_id must be rejected before any copy, leaving no
    workspace behind (GRO-172 / H1)."""
    with pytest.raises(WorkspaceError, match="template not found"):
        manager.create(name="evil", owner="mallory", template_id=bad_id)
    assert list(manager.workspaces_dir.iterdir()) == []


def test_create_traversal_does_not_copy_external_dir(manager, data_root):
    """The classic exploit: `../evil` would resolve to a sibling of templates/
    and copy its contents into the member workspace. The charset guard rejects
    it, so the secret file must never land in any workspace."""
    evil = data_root / "evil"
    evil.mkdir()
    (evil / "secret.txt").write_text("id_rsa contents")

    with pytest.raises(WorkspaceError):
        manager.create(name="pwn", owner="mallory", template_id="../evil")

    assert list(manager.workspaces_dir.iterdir()) == []
    # The external secret was never copied anywhere under workspaces/.
    assert not any(manager.workspaces_dir.rglob("secret.txt"))


def test_create_rollback_on_copy_failure(manager, data_root):
    """A mid-copy failure (e.g. stale template with .micro-eval/ conflicts,
    or any OSError during shutil.copytree/copy2) must not leave a partial
    workspace directory behind, and must surface a readable WorkspaceError."""
    tpl_dir = data_root / "templates" / "tpl-bad"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "eval.yaml").write_text("project_name: tpl-bad\n")
    (tpl_dir / "template.json").write_text(
        '{"schema_version":"1.0","template_id":"tpl-bad","name":"Bad","version":"1.0.0","created_at":"","updated_at":""}'
    )

    with patch("shutil.copy2", side_effect=OSError("disk full")):
        with pytest.raises(WorkspaceError, match="workspace creation failed"):
            manager.create(name="fail", owner="alice", template_id="tpl-bad")

    assert list(manager.workspaces_dir.iterdir()) == []


def test_workspace_id_format(manager):
    meta = manager.create(name="x", owner="a")
    assert re.match(r"^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$", meta.workspace_id)


def test_list_active_only(manager):
    manager.create(name="a", owner="alice")
    meta_b = manager.create(name="b", owner="bob")
    manager.update(meta_b.workspace_id, status="archived")
    active = manager.list_workspaces(include_archived=False)
    assert len(active) == 1
    all_ws = manager.list_workspaces(include_archived=True)
    assert len(all_ws) == 2


def test_lifecycle(manager):
    meta = manager.create(name="x", owner="alice")
    assert meta.status == "active"
    manager.update(meta.workspace_id, status="archived")
    updated = manager.get(meta.workspace_id)
    assert updated.status == "archived"
    assert manager.delete(meta.workspace_id)
    assert manager.get(meta.workspace_id) is None


def test_path_traversal_rejected(manager):
    assert manager.resolve_path("../../../etc/passwd") is None
    assert manager.resolve_path("ws-not-matching-format") is None


def test_symlink_escape(manager, data_root):
    secret = data_root.parent / "secret"
    secret.mkdir()
    (secret / "workspace.json").write_text(
        '{"workspace_id":"x","name":"x","owner":"x","created_at":"x","status":"active","schema_version":"1.0"}'
    )
    fake_id = "ws-20260619T000000Z-aaaaaaaa"
    link = manager.workspaces_dir / fake_id
    os.symlink(str(secret), str(link))
    assert manager.resolve_path(fake_id) is None


def test_delete_removes_directory(manager):
    meta = manager.create(name="x", owner="alice")
    ws_dir = manager.workspaces_dir / meta.workspace_id
    assert ws_dir.exists()
    manager.delete(meta.workspace_id)
    assert not ws_dir.exists()
