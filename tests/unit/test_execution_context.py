"""Filesystem and cancellation boundaries of one provider execution context."""
import asyncio
import os
import threading
from pathlib import Path

import pytest

from micro_eval.engine.execution import ExecutionContext, copy_bounded_outputs
from micro_eval.engine.providers.base import IsolationLevel, WorkspaceHandle
from micro_eval.engine.providers.git_worktree import GitWorktreeProvider, WorkspaceProviderError
from micro_eval.engine.workspace import WorkspaceManager
from micro_eval.models.task import WorkspaceSpec


def test_copy_only_private_files_and_bound_aggregate(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir(); output.mkdir()
    secret = tmp_path / "secret"
    secret.write_text("never-copy")
    (source / "link").symlink_to(secret)
    os.link(secret, source / "hard")
    os.mkfifo(source / "fifo")
    (source / "a.txt").write_text("hello")
    (source / "b.txt").write_text("too-large")
    assert copy_bounded_outputs(source, output, 5)
    assert sorted(p.name for p in output.iterdir()) == ["a.txt"]
    assert (output / "a.txt").read_text() == "hello"
    assert secret.read_text() == "never-copy"


def test_copy_rejects_directory_symlink_and_private_temp(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir(); output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(); (outside / "secret").write_text("never-copy")
    (source / "linked").symlink_to(outside, target_is_directory=True)
    (source / ".tmp").mkdir(); (source / ".tmp" / "private").write_text("temporary")
    assert copy_bounded_outputs(source, output, 100)
    assert not list(output.iterdir())


def test_copy_refuses_hardlinked_destination_before_truncation(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir(); output.mkdir()
    secret = tmp_path / "secret"
    secret.write_text("untouched")
    os.link(secret, output / "value")
    (source / "value").write_text("replace")
    with pytest.raises(WorkspaceProviderError, match="private regular"):
        copy_bounded_outputs(source, output, 100)
    assert secret.read_text() == "untouched"


@pytest.mark.asyncio
async def test_input_hardlink_refused_before_truncation(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret"
    secret.write_text("untouched")
    target = workspace / "input.txt"
    os.link(secret, target)
    context = ExecutionContext(GitWorktreeProvider(tmp_path), WorkspaceHandle(
        workspace, "git_worktree", IsolationLevel.logical,
    ))
    with pytest.raises(WorkspaceProviderError, match="private regular"):
        await context.write_file(target, b"replace")
    assert secret.read_text() == "untouched"


@pytest.mark.asyncio
async def test_cancellation_during_cleanup_propagates_after_cleanup(tmp_path, monkeypatch):
    manager = WorkspaceManager(tmp_path)
    prepared = manager.prepare(cell_id="cell", workspace=WorkspaceSpec())
    entered = threading.Event()
    release = threading.Event()
    original = prepared.execution_context.provider.cleanup

    def cleanup(handle):
        entered.set()
        assert release.wait(5)
        original(handle)

    monkeypatch.setattr(prepared.execution_context.provider, "cleanup", cleanup)
    task = asyncio.create_task(manager.cleanup_workspace_async(prepared))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert prepared.snapshot.cleanup_status == "cleaned"
    assert not prepared.path.exists()
