"""Security negative tests for server mode."""

import re

import pytest

from micro_eval.server.queue import QueueDB
from micro_eval.server.workspace import WorkspaceManager


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    (root / "workspaces").mkdir()
    return root


class TestPathTraversal:
    def test_dot_dot(self, data_root):
        mgr = WorkspaceManager(data_root)
        assert mgr.resolve_path("ws-../../../etc") is None

    def test_null_byte(self, data_root):
        mgr = WorkspaceManager(data_root)
        assert mgr.resolve_path("ws-\x00-exploit") is None

    def test_invalid_format(self, data_root):
        mgr = WorkspaceManager(data_root)
        assert mgr.resolve_path("not-a-workspace-id") is None


class TestMemberNameValidation:
    def test_valid_names(self):
        pattern = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
        assert pattern.match("alice")
        assert pattern.match("Bob.Smith")
        assert pattern.match("user-123")
        assert pattern.match("a_b.c-d")

    def test_invalid_names(self):
        pattern = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
        assert not pattern.match("")
        assert not pattern.match("a" * 65)
        assert not pattern.match("alice; rm -rf /")
        assert not pattern.match("alice<script>")
        assert not pattern.match("alice bob")


class TestWorkspaceQueueInterlock:
    def test_delete_with_pending_job_blocked(self, data_root):
        mgr = WorkspaceManager(data_root)
        meta = mgr.create(name="test", owner="alice")
        db = QueueDB(data_root / "queue.db")
        db.enqueue(meta.workspace_id, "alice", '{"run_id": "r1"}')
        assert db.has_pending_jobs(meta.workspace_id)
        db.close()

    def test_no_pending_jobs_allows_delete(self, data_root):
        mgr = WorkspaceManager(data_root)
        meta = mgr.create(name="test", owner="alice")
        db = QueueDB(data_root / "queue.db")
        assert not db.has_pending_jobs(meta.workspace_id)
        assert mgr.delete(meta.workspace_id)
        db.close()
