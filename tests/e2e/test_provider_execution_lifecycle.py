"""Cell-level provider routing, resource ownership and failure isolation."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from micro_eval.config.planner import build_run_plan
from micro_eval.engine.cell_lifecycle import CellLifecycle
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.engine.providers.base import CommandResult, IsolationLevel, ProviderRegistry
from micro_eval.engine.providers.git_worktree import GitWorktreeProvider
from micro_eval.engine.workspace import WorkspaceManager
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, Guardrails, ProjectConfigV2
from micro_eval.models.task import TaskSpec, WorkspaceSpec


def make_plan(root, *, tasks=1, workspace=None, agent_env=None):
    config = ProjectConfigV2(
        project_name="provider-routing",
        configurations=[ConfigurationSpec(id="agent", name="Agent", agent=AgentSpec(
            name="spy", command=["agent-only"], env=agent_env or {},
        ))],
        guardrails=Guardrails(max_concurrency=2),
    )
    config.config_hash = "provider-routing"
    return build_run_plan(config, [TaskSpec(
        id=f"task-{i}", name=f"Task {i}", input_payload=f"input-{i}",
        workspace=workspace or WorkspaceSpec(setup=[["setup-only"]]),
        expectations=[{"type": "command", "command": ["validator-only"]}],
    ) for i in range(tasks)], project_root=root)


class SpyProvider(GitWorktreeProvider):
    def __init__(self, root):
        super().__init__(root)
        self.events = []
        self.handles = []
        self.started = asyncio.Event()
        self.block = False
        self.fail_setup = False
        self.crash = False

    def create(self, spec, **kwargs):
        assert not spec.setup, "setup must be deferred until context exists"
        handle = super().create(spec, **kwargs)
        handle.provider_name = "spy"
        self.handles.append(handle)
        self.events.append((id(handle), "create"))
        return handle

    async def execute(self, handle, request):
        self.events.append((id(handle), request.argv[0]))
        assert request.cwd == handle.workspace_path
        if request.argv == ["setup-only"] and self.fail_setup:
            return CommandResult(exit_code=7, stderr="setup failed")
        if request.argv == ["agent-only"]:
            self.started.set()
            if self.block:
                await asyncio.Event().wait()
            if self.crash:
                raise RuntimeError("agent-env-secret")
            assert request.stdin.startswith(b"input-")
        await asyncio.sleep(0)
        return CommandResult(exit_code=0, stdout="provider-output")

    def observe_final(self, handle, **kwargs):
        self.events.append((id(handle), "observe"))
        return super().observe_final(handle, **kwargs)

    def cleanup(self, handle):
        self.events.append((id(handle), "cleanup"))
        super().cleanup(handle)


def install_provider(monkeypatch, root):
    spy = SpyProvider(root)
    original = WorkspaceManager.__init__

    def init(manager, *args, **kwargs):
        original(manager, *args, **kwargs)
        manager._registry = ProviderRegistry()
        manager._registry.register(spy)

    async def no_host_spawn(*args, **kwargs):
        pytest.fail("agent or validator bypassed its provider")

    monkeypatch.setattr(WorkspaceManager, "__init__", init)
    monkeypatch.setattr("micro_eval.engine.adapter.run_process", no_host_spawn)
    monkeypatch.setattr("micro_eval.evaluation.validator.run_process", no_host_spawn)
    return spy


@pytest.mark.asyncio
async def test_two_cells_route_setup_agent_observation_validator_cleanup_to_owner(tmp_path, monkeypatch):
    spy = install_provider(monkeypatch, tmp_path)
    record = await ExecutionKernel(tmp_path).run(make_plan(tmp_path, tasks=2))
    assert [r.status.value for r in record.results] == ["pass", "pass"]
    assert len(spy.handles) == 2
    assert spy.handles[0].workspace_path != spy.handles[1].workspace_path
    for handle in spy.handles:
        assert [stage for owner, stage in spy.events if owner == id(handle)] == [
            "create", "setup-only", "agent-only", "observe", "validator-only", "cleanup",
        ]
        assert not handle.workspace_path.exists()
    assert all(r.cell_snapshot.cleanup_status == "cleaned" for r in record.results)
    assert all(r.stdout_summary == "provider-output" for r in record.results)


@pytest.mark.asyncio
async def test_setup_failure_retains_exit_and_never_starts_agent_or_validator(tmp_path, monkeypatch):
    spy = install_provider(monkeypatch, tmp_path)
    spy.fail_setup = True
    record = await ExecutionKernel(tmp_path).run(make_plan(tmp_path))
    assert record.results[0].status.value == "error"
    assert record.results[0].cell_snapshot.setup_exit_code == 7
    stages = [stage for _, stage in spy.events]
    assert "agent-only" not in stages
    assert "validator-only" not in stages
    assert stages.count("cleanup") == 1


@pytest.mark.asyncio
async def test_unexpected_invoke_failure_cleans_once_and_redacts_configuration_secret(tmp_path, monkeypatch):
    spy = install_provider(monkeypatch, tmp_path)
    spy.crash = True
    record = await ExecutionKernel(tmp_path).run(make_plan(tmp_path, agent_env={
        "MICRO_EVAL_SECRET_LOCAL": "agent-env-secret",
    }))
    assert record.results[0].status.value == "error"
    assert "agent-env-secret" not in record.model_dump_json()
    assert [stage for _, stage in spy.events].count("cleanup") == 1
    assert not spy.handles[0].workspace_path.exists()


@pytest.mark.asyncio
async def test_task_cancellation_waits_for_provider_cleanup(tmp_path, monkeypatch):
    spy = install_provider(monkeypatch, tmp_path)
    spy.block = True
    running = asyncio.create_task(ExecutionKernel(tmp_path).run(make_plan(tmp_path)))
    await asyncio.wait_for(spy.started.wait(), 5)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert [stage for _, stage in spy.events].count("cleanup") == 1
    assert not spy.handles[0].workspace_path.exists()


@pytest.mark.asyncio
async def test_nonlogical_conversation_rejected_before_allocating_workspace(tmp_path, monkeypatch):
    spy = install_provider(monkeypatch, tmp_path)
    monkeypatch.setattr(CellLifecycle, "_uses_conversation", lambda *_: True)
    record = await ExecutionKernel(tmp_path).run(make_plan(tmp_path, workspace=WorkspaceSpec(
        isolation_level=IsolationLevel.os_policy,
    )))
    assert record.results[0].status.value == "error"
    assert "only by logical" in record.results[0].stderr_summary
    assert not spy.events


@pytest.mark.asyncio
async def test_cancel_during_create_joins_creator_and_cleans_its_result(tmp_path, monkeypatch):
    spy = install_provider(monkeypatch, tmp_path)
    entered = threading.Event()
    release = threading.Event()
    original = spy.create

    def delayed_create(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    spy.create = delayed_create
    running = asyncio.create_task(ExecutionKernel(tmp_path).run(make_plan(tmp_path)))
    await asyncio.to_thread(entered.wait, 5)
    running.cancel()
    await asyncio.sleep(0)
    assert not running.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert [stage for _, stage in spy.events] == ["create", "cleanup"]
    assert not spy.handles[0].workspace_path.exists()


@pytest.mark.asyncio
async def test_stdout_mode_can_validate_unexported_files_without_retaining_raw_secret(tmp_path):
    plan = make_plan(tmp_path, workspace=WorkspaceSpec(), agent_env={
        "MICRO_EVAL_SECRET_TEST": "private-output-secret",
    })
    plan.cells[0].configuration.agent.command = ["{python}", "-c", (
        "import os; from pathlib import Path; "
        "Path(os.environ['MICRO_EVAL_OUTPUT_DIR'],'extra.txt').write_text(os.environ['MICRO_EVAL_SECRET_TEST']); "
        "print('safe-output')"
    )]
    from micro_eval.models.task import ExpectationSpec
    plan.cells[0].task.expectations = [ExpectationSpec(type="file_exists", value="{output_dir}/extra.txt")]
    record = await ExecutionKernel(tmp_path).run(plan)
    assert record.results[0].status.value == "pass", record.results[0].model_dump()
    run = tmp_path / ".micro-eval" / "runs" / plan.run_id
    assert not list(run.rglob("extra.txt"))
    assert not list(run.rglob(".micro-eval-receive-*"))
    assert not list((tmp_path / ".micro-eval" / "workspaces").rglob(".micro-eval-io-*"))
    for path in (run / "cells").rglob("*"):
        if path.is_file():
            assert b"private-output-secret" not in path.read_bytes()


@pytest.mark.asyncio
async def test_logical_conversation_uses_provider_bridge_and_private_output(tmp_path, monkeypatch):
    import sys
    from micro_eval.models.run import AdapterResult, CellStatus

    plan = make_plan(tmp_path, workspace=WorkspaceSpec(), agent_env={
        "MICRO_EVAL_SECRET_TEST": "conversation-private-secret",
    })
    plan.cells[0].task.expectations = []
    plan.cells[0].configuration.agent.command = ["{python}", "-c", (
        "import os,json,sys; from pathlib import Path; "
        "Path(os.environ['MICRO_EVAL_OUTPUT_DIR'],'extra.txt').write_text(os.environ['MICRO_EVAL_SECRET_TEST']); "
        "json.loads(sys.stdin.readline()); print(json.dumps({'content':'safe-reply'}))"
    )]
    monkeypatch.setattr(CellLifecycle, "_uses_conversation", lambda *_: True)
    observed = []

    async def simulate(**kwargs):
        bridge = kwargs["bridge"]
        observed.append(bridge)
        assert bridge.agent.command[0] == sys.executable
        assert Path(bridge.env["MICRO_EVAL_OUTPUT_DIR"]).name.startswith(".micro-eval-io-")
        await bridge.start()
        try:
            assert await bridge.send_turn("hello") == "safe-reply"
        finally:
            code, stderr = await bridge.stop()
        return object(), AdapterResult(status=CellStatus.passed, exit_code=code, stderr=stderr), [
            {"role":"assistant", "content":"safe-reply"},
        ]

    async def score(**kwargs):
        return None

    monkeypatch.setattr("micro_eval.engine.cell_lifecycle.simulate_conversation", simulate)
    monkeypatch.setattr("micro_eval.engine.cell_lifecycle.score_conversation", score)
    record = await ExecutionKernel(tmp_path).run(plan)
    assert len(observed) == 1
    assert record.results[0].status.value == "pass", record.results[0].model_dump()
    assert not list((tmp_path / ".micro-eval").rglob("extra.txt"))
    assert not list((tmp_path / ".micro-eval").rglob(".micro-eval-io-*"))
