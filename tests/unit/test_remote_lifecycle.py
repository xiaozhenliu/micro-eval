"""Stateful offline SDK contracts; these do not attest cloud isolation."""

from __future__ import annotations

import asyncio
import json
import os
import selectors
import shlex
import signal
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from micro_eval.engine.execution import ExecutionContext
from micro_eval.engine.providers.base import ExecutionRequest
from micro_eval.engine.providers.git_worktree import WorkspaceProviderError
from micro_eval.engine.providers.remote import (
    E2BProvider, ModalProvider, E2B_API_KEY_ENV, MODAL_TOKEN_ID_ENV, MODAL_TOKEN_SECRET_ENV,
)
from micro_eval.models.task import NetworkPolicy, WorkspaceSpec, WorkspaceType


class _Dual:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)

    async def aio(self, *args, **kwargs):
        return await asyncio.to_thread(self.fn, *args, **kwargs)


class _Reader:
    def __init__(self, pipe):
        self.pipe = pipe

    def __iter__(self):
        while data := self.pipe.read(8192):
            yield data

    def read(self, n=-1):
        return self.pipe.read(n)

    async def __aiter__(self):
        while data := await asyncio.to_thread(self.pipe.read, 8192):
            yield data


class _Process:
    def __init__(self, process):
        self.process = process
        self.stdout = _Reader(process.stdout)
        self.stderr = _Reader(process.stderr)
        self.wait = _Dual(self.wait)

    @property
    def returncode(self):
        return self.process.returncode

    def wait(self):
        return self.process.wait(timeout=10)


class _Sandbox:
    """A local subprocess is only the test double for a remote control API."""
    def __init__(self, settings):
        self.settings = settings
        self.commands = self
        self.sandbox_id = "fake-e2b"
        self.object_id = "fake-modal"
        self.processes = []
        self.kills = 0
        self.failed_kill = False
        self.started = threading.Event()
        self.calls = []
        self.exec = _Dual(self.exec)
        self.terminate = _Dual(self.terminate)

    def _launch(self, argv):
        self.calls.append(argv)
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        self.processes.append(process)
        self.started.set()
        return process

    def run(self, command, *, timeout, on_stdout=None, on_stderr=None, **kwargs):
        process = self._launch(shlex.split(command))
        sel = selectors.DefaultSelector()
        for name in ("stdout", "stderr"):
            sel.register(getattr(process, name), selectors.EVENT_READ, name)
        streams = {"stdout": bytearray(), "stderr": bytearray()}
        try:
            while sel.get_map():
                for key, _ in sel.select(timeout=5):
                    data = os.read(key.fileobj.fileno(), 4096)
                    if not data:
                        sel.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    callback = on_stdout if key.data == "stdout" else on_stderr
                    if callback:
                        callback(data.decode())
                    streams[key.data].extend(data)
        finally:
            sel.close()
        return SimpleNamespace(exit_code=process.wait(timeout=10),
                               stdout=streams["stdout"].decode(), stderr=streams["stderr"].decode())

    def exec(self, *argv, timeout, **kwargs):
        return _Process(self._launch(list(argv)))

    def kill(self, **kwargs):
        self.kills += 1
        if self.failed_kill:
            raise RuntimeError("transport failure")
        for process in self.processes:
            if process.poll() is None:
                # Wrapper starts the actual command as a separate session.
                # Kill descendants too to model whole-sandbox destruction.
                children = subprocess.run(["pgrep", "-P", str(process.pid)], capture_output=True, text=True)
                for pid in children.stdout.split():
                    try:
                        os.killpg(int(pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        return True

    def terminate(self, wait=True):
        self.kill()


@pytest.fixture(params=[E2BProvider, ModalProvider], ids=["e2b", "modal"])
def remote(request, monkeypatch, tmp_path):
    sandboxes = []
    clients = []

    def create(**kwargs):
        sandbox = _Sandbox(kwargs)
        sandboxes.append(sandbox)
        return sandbox

    def credentials(*args):
        clients.append(args)
        return SimpleNamespace(token_id=args[0])

    monkeypatch.setenv(E2B_API_KEY_ENV, "control-e2b-key")
    monkeypatch.setenv(MODAL_TOKEN_ID_ENV, "control-modal-id")
    monkeypatch.setenv(MODAL_TOKEN_SECRET_ENV, "control-modal-secret")
    monkeypatch.setitem(sys.modules, "e2b", SimpleNamespace(Sandbox=SimpleNamespace(create=create)))
    monkeypatch.setitem(sys.modules, "modal", SimpleNamespace(
        Client=SimpleNamespace(from_credentials=_Dual(credentials)),
        App=SimpleNamespace(lookup=_Dual(lambda *a, **kw: (a, kw))),
        Image=SimpleNamespace(debian_slim=lambda **kw: kw),
        Sandbox=SimpleNamespace(create=_Dual(create), from_name=_Dual(lambda *a, **kw: sandboxes[-1])),
    ))
    project = tmp_path / "project"
    project.mkdir()
    provider = request.param(project)
    provider.root = tmp_path / "remote-filesystem"
    return provider, project, sandboxes, clients


def test_complete_cell_persists_sources_setup_agent_validation_and_output(remote, tmp_path):
    provider, project, sandboxes, clients = remote
    source = project / "fixture"
    source.mkdir()
    (source / "input.txt").write_text("fixture")
    (source / ".git").mkdir()
    (source / ".git" / "config").write_text("host git configuration")
    handle = provider.create(WorkspaceSpec(type=WorkspaceType.files, files=["fixture"],
        setup=[["python3", "-c", "from pathlib import Path;Path('setup.txt').write_text('ready')"]]),
        cell_id="cell", run_id="run")
    assert handle.is_remote
    assert handle.setup_exit_code == 0
    assert len(sandboxes) == 1
    assert not (handle.workspace_path / "fixture" / ".git").exists()
    context = ExecutionContext(provider, handle)
    host_output = tmp_path / "host-output"

    async def run():
        output = await context.prepare_output(host_output)
        await context.write_file(output / "input.txt", b"task input")
        result = await context.execute(ExecutionRequest([
            "python3", "-c", "from pathlib import Path;import os,sys;"
            "assert Path('fixture/input.txt').read_text()=='fixture';"
            "assert Path('setup.txt').read_text()=='ready';"
            "assert os.environ['TASK_SECRET']=='task-value';"
            "assert 'MICRO_EVAL_SECRET_E2B_API_KEY' not in os.environ;"
            "Path(sys.argv[1]).write_text(sys.stdin.read());print('agent complete')", str(output / "answer.txt")],
            stdin=b"answer from stdin", env={"TASK_SECRET": "task-value"}, timeout_s=5))
        assert result.stdout == "agent complete\n"
        validation = await context.execute(ExecutionRequest([
            "python3", "-c", "from pathlib import Path;import sys;assert Path(sys.argv[1]).read_text()=='answer from stdin'",
            str(output / "answer.txt")], timeout_s=5))
        assert validation.exit_code == 0
        assert await context.path_exists(output / "answer.txt")
        assert not await context.path_exists(output / "missing")
        receiving = tmp_path / ".micro-eval-receive-contract"
        assert not await context.collect_output(output, receiving, 1024)
        assert (receiving / "answer.txt").read_text() == "answer from stdin"
        assert not (receiving / "input.txt").exists()

    asyncio.run(run())
    assert provider.observe_final(handle, byte_limit=100).warnings == ("observation_unavailable",)
    provider.cleanup(handle)
    assert sandboxes[0].kills == 1
    assert handle.metadata["sandbox_cleanup"] == "confirmed"
    with pytest.raises(WorkspaceProviderError, match="unavailable"):
        provider.exec_command(handle, ["true"])


@pytest.mark.parametrize("policy", [NetworkPolicy.full, NetworkPolicy.none])
def test_network_requested_is_bound_to_create_policy(remote, policy):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(network_policy=policy), cell_id="cell", run_id="run")
    assert handle.metadata["network_policy_requested"] == policy.value
    assert handle.metadata["network_policy_effective"] == policy.value
    if provider.name == "e2b":
        assert sandboxes[0].settings["allow_internet_access"] == (policy == NetworkPolicy.full)
    else:
        assert sandboxes[0].settings["block_network"] == (policy == NetworkPolicy.none)
        assert sandboxes[0].settings["client"].token_id == "control-modal-id"
    provider.cleanup(handle)


def test_allowlist_fails_before_remote_creation(remote):
    provider, _, sandboxes, _ = remote
    with pytest.raises(WorkspaceProviderError, match="allowlist"):
        provider.create(WorkspaceSpec(network_policy=NetworkPolicy.allowlist), cell_id="cell", run_id="run")
    assert not sandboxes


def test_output_capped_independently_while_both_streams_drained(remote):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    result = asyncio.run(provider.execute(handle, ExecutionRequest([
        "python3", "-c", "import os;os.write(1,b'x'*1000000);os.write(2,b'y'*1000000)"],
        timeout_s=5, output_cap_bytes=127)))
    assert result.exit_code == 0
    assert result.stdout == "x" * 127
    assert result.stderr == "y" * 127
    assert result.stdout_truncated and result.stderr_truncated
    provider.cleanup(handle)


def test_timeout_destroys_owned_sandbox(remote):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    result = asyncio.run(provider.execute(handle, ExecutionRequest(
        ["python3", "-c", "import time;time.sleep(30)"], timeout_s=.1)))
    assert result.timed_out
    assert sandboxes[0].kills == 1
    assert handle.metadata["sandbox_cleanup"] == "confirmed"


def test_cancellation_destroys_owned_sandbox(remote):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    sandboxes[0].started.clear()

    async def run():
        task = asyncio.create_task(provider.execute(handle, ExecutionRequest(
            ["python3", "-c", "import time;time.sleep(30)"], timeout_s=10)))
        await asyncio.to_thread(sandboxes[0].started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert sandboxes[0].kills == 1
    assert handle.metadata["sandbox_cleanup"] == "confirmed"


def test_cleanup_failure_is_recorded_and_not_erased_by_retry(remote):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    sandboxes[0].failed_kill = True
    with pytest.raises(WorkspaceProviderError, match="termination failed"):
        provider.cleanup(handle)
    assert handle.metadata["sandbox_cleanup"] == "failed"
    sandboxes[0].failed_kill = False
    provider.cleanup(handle)
    assert handle.metadata["sandbox_cleanup"] == "failed"
    assert handle.metadata["sandbox_cleanup_retry"] == "confirmed"


def test_setup_exit_status_is_real(remote):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(setup=[["python3", "-c", "raise SystemExit(7)"], ["false"]]),
        cell_id="cell", run_id="run")
    assert handle.setup_exit_code == 7
    provider.cleanup(handle)


def test_control_credentials_rejected_even_under_another_name(remote):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    before = len(sandboxes[0].calls)
    key = "control-e2b-key" if provider.name == "e2b" else "control-modal-secret"
    for env in ({"E2B_API_KEY": "different"}, {"TASK_SECRET": key}):
        with pytest.raises(WorkspaceProviderError, match="credential"):
            provider.exec_command(handle, ["true"], env=env)
    assert len(sandboxes[0].calls) == before
    provider.cleanup(handle)


def test_source_symlink_rejected_and_creation_failure_destroys_sandbox(remote, tmp_path):
    provider, project, sandboxes, _ = remote
    outside = tmp_path / "outside"
    outside.write_text("host secret")
    (project / "escape").symlink_to(outside)
    with pytest.raises(WorkspaceProviderError, match="symlink"):
        provider.create(WorkspaceSpec(type=WorkspaceType.files, files=["escape"]), cell_id="cell", run_id="run")
    assert sandboxes[0].kills == 1


def test_output_transfer_skips_links_oversize_and_caps_total(remote, tmp_path):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    destination = tmp_path / "download"
    output = provider.prepare_output(handle, destination)
    (output / "small.txt").write_text("small")
    (output / "oversize.txt").write_bytes(b"x" * 10000)
    (output / "symlink").symlink_to(tmp_path / "outside")
    (output / "linked.txt").write_text("linked")
    os.link(output / "linked.txt", output / "hardlink")
    os.mkfifo(output / "fifo")
    assert provider.collect_output(handle, output, destination, 20)
    assert [p.name for p in destination.iterdir()] == ["small.txt"]
    provider.cleanup(handle)


def test_input_write_rejects_remote_parent_symlink(remote, tmp_path):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    victim = tmp_path / "victim"
    victim.mkdir()
    (handle.workspace_path / "link").symlink_to(victim, target_is_directory=True)
    with pytest.raises(WorkspaceProviderError, match="transfer failed"):
        provider.write_file(handle, handle.workspace_path / "link" / "stolen", b"write")
    assert not (victim / "stolen").exists()
    provider.cleanup(handle)


def test_git_upload_uses_selected_commit_and_excludes_host_git_metadata(remote):
    provider, project, _, _ = remote
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "version.txt").write_text("first")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-qm", "first"], cwd=project, check=True)
    ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    (project / "version.txt").write_text("second")
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-qam", "second"], cwd=project, check=True)
    handle = provider.create(WorkspaceSpec(type=WorkspaceType.git_repo, ref=ref), cell_id="cell", run_id="run")
    assert (handle.workspace_path / "version.txt").read_text() == "first"
    assert not (handle.workspace_path / ".git").exists()
    assert (project / "version.txt").read_text() == "second"
    assert not list((project / ".micro-eval" / "workspaces").glob("remote-upload-*"))
    with pytest.raises(NotImplementedError):
        provider.snapshot(handle)
    provider.cleanup(handle)


@pytest.mark.parametrize("selection", [".git", ".git/config", ".codex", ".agents/settings"])
def test_explicit_control_source_is_rejected(remote, selection):
    provider, project, sandboxes, _ = remote
    source = project / selection
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("control data")
    with pytest.raises(WorkspaceProviderError, match="control directory"):
        provider.create(WorkspaceSpec(type=WorkspaceType.files, files=[selection]), cell_id="cell", run_id="run")
    assert sandboxes[0].kills == 1


def test_large_stdin_uses_bounded_file_upload(remote):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    result = asyncio.run(provider.execute(handle, ExecutionRequest(
        ["python3", "-c", "import sys;print(len(sys.stdin.buffer.read()))"], stdin=b"x" * 300000,
        timeout_s=10, output_cap_bytes=100)))
    assert result.stdout == "300000\n"
    assert not list(handle.workspace_path.glob(".micro-eval-input-*"))
    provider.cleanup(handle)


def test_control_stream_overflow_destroys_sandbox(remote, monkeypatch):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    original = sandboxes[0]._launch
    monkeypatch.setattr(sandboxes[0], "_launch", lambda argv: original(
        ["python3", "-c", "import os;os.write(1,b'x'*100000)"]))
    with pytest.raises(WorkspaceProviderError, match="transport failed"):
        asyncio.run(provider.execute(handle, ExecutionRequest(["true"], timeout_s=10, output_cap_bytes=1)))
    assert sandboxes[0].kills == 1
    assert handle.metadata["sandbox_cleanup"] == "confirmed"


def test_sdk_exception_named_timeout_is_not_a_deadline(remote, monkeypatch):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    def failure(*args, **kwargs):
        raise RuntimeError("timeout appears in unrelated text")
    monkeypatch.setattr(provider, "_run", failure)
    with pytest.raises(WorkspaceProviderError, match="transport failed"):
        provider.exec_command(handle, ["true"], timeout_s=1)
    provider.cleanup(handle)


def test_repeated_cancellation_waits_for_cleanup(remote, monkeypatch):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    sandbox = sandboxes[0]
    sandbox.started.clear()
    kill_started = threading.Event()
    release_kill = threading.Event()
    original = provider._kill
    def slow_kill(sb):
        kill_started.set()
        assert release_kill.wait(5)
        original(sb)
    monkeypatch.setattr(provider, "_kill", slow_kill)

    async def run():
        task = asyncio.create_task(provider.execute(handle, ExecutionRequest(
            ["python3", "-c", "import time;time.sleep(30)"], timeout_s=10)))
        assert await asyncio.to_thread(sandbox.started.wait, 5)
        task.cancel()
        assert await asyncio.to_thread(kill_started.wait, 5)
        task.cancel()
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done()
        release_kill.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert handle.metadata["sandbox_cleanup"] == "confirmed"


def test_transfer_rejects_untrusted_inventory_paths(remote, tmp_path, monkeypatch):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    output = provider.prepare_output(handle, tmp_path / "download")
    original = provider._files
    def forged(h, payload):
        if payload["op"] == "list":
            return {"skipped": False, "entries": [
                {"path": "../escape", "size": 0}, {"path": "/absolute", "size": 0},
                {"path": ".git/config", "size": 0}, {"path": ".", "size": 0},
                {"path": "good", "size": -1}, {"path": "boolean", "size": True}]}
        raise AssertionError("unsafe inventory must be rejected before body fetch")
    monkeypatch.setattr(provider, "_files", forged)
    assert provider.collect_output(handle, output, tmp_path / "download", 100)
    monkeypatch.setattr(provider, "_files", original)
    provider.cleanup(handle)


def test_timeout_collect_output_preserves_timeout_outcome(remote, tmp_path):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    output = provider.prepare_output(handle, tmp_path / "download")
    result = asyncio.run(provider.execute(handle, ExecutionRequest(
        ["python3", "-c", "import time;time.sleep(30)"], timeout_s=.1)))
    assert result.timed_out
    assert provider.collect_output(handle, output, tmp_path / "download", 100)
    assert handle.metadata["output_transfer"] == "unavailable_after_termination"


def test_actual_adapter_uses_remote_file_io_and_exports_only_redacted_selection(remote, tmp_path, monkeypatch):
    from micro_eval.engine.adapter import AgentAdapter
    from micro_eval.models.configuration import AgentSpec, InputMode, OutputMode
    from micro_eval.models.run import CellStatus

    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    context = ExecutionContext(provider, handle)
    monkeypatch.setenv("MICRO_EVAL_SECRET_TASK", "test-task-secret")
    destination = tmp_path / "cell-artifacts"
    script = ("from pathlib import Path;import sys,os;"
              "assert Path(sys.argv[1]).read_text()=='user question';"
              "secret=os.environ['MICRO_EVAL_SECRET_TASK'];"
              "Path(sys.argv[2]).write_text('answer '+secret);"
              "Path(sys.argv[3],'unselected.txt').write_text(secret);print(secret)")
    result, _ = asyncio.run(AgentAdapter(output_cap_bytes=4096).invoke(
        agent=AgentSpec(name="remote-file-agent", command=["{python}", "-c", script,
            "{input_file}", "{output_file}", "{output_dir}"],
            input_mode=InputMode.file, output_mode=OutputMode.file,
            required_secrets=["MICRO_EVAL_SECRET_TASK"]),
        input_payload="user question", cwd=tmp_path, output_dir=destination,
        execution_context=context,
    ))
    assert result.status == CellStatus.passed
    assert result.output == "answer [REDACTED:MICRO_EVAL_SECRET_TASK]"
    assert "test-task-secret" not in result.stdout
    assert (destination / "output.txt").read_text() == result.output
    assert not (destination / "unselected.txt").exists()
    assert not list(tmp_path.glob(".micro-eval-receive-*"))
    provider.cleanup(handle)


def test_missing_sdk_identity_rolls_back_created_sandbox(remote, monkeypatch):
    provider, _, sandboxes, _ = remote
    original = provider._start
    def missing(policy):
        sandbox = original(policy)
        delattr(sandbox, "sandbox_id" if provider.name == "e2b" else "object_id")
        return sandbox
    monkeypatch.setattr(provider, "_start", missing)
    with pytest.raises(AttributeError):
        provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    assert sandboxes[0].kills == 1


def test_modal_create_deadline_reconciles_and_terminates_orphan(remote, monkeypatch):
    provider, _, sandboxes, _ = remote
    if provider.name != "modal":
        pytest.skip("Modal-specific async SDK control plane")
    import micro_eval.engine.providers.remote as remote_module
    monkeypatch.setattr(remote_module, "CONTROL_TIMEOUT_S", .03)
    create_api = sys.modules["modal"].Sandbox.create
    cancelled = threading.Event()
    async def interrupted_create(**kwargs):
        create_api.fn(**kwargs)  # control plane created a sandbox before losing its response
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(create_api, "aio", interrupted_create)
    with pytest.raises(WorkspaceProviderError, match="reconciled sandbox was terminated"):
        provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    assert cancelled.is_set()
    assert sandboxes[0].settings["name"].startswith("micro-eval-")
    assert sandboxes[0].kills == 1


def test_modal_unknown_creation_cleanup_is_not_reported_as_success(remote, monkeypatch):
    provider, _, _, _ = remote
    if provider.name != "modal":
        pytest.skip("Modal-specific async SDK control plane")
    import micro_eval.engine.providers.remote as remote_module
    monkeypatch.setattr(remote_module, "CONTROL_TIMEOUT_S", .02)
    monkeypatch.setattr(remote_module, "RECONCILE_TIMEOUT_S", .02)
    cancelled = []
    async def blocked(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    monkeypatch.setattr(sys.modules["modal"].Sandbox.create, "aio", blocked)
    monkeypatch.setattr(sys.modules["modal"].Sandbox.from_name, "aio", blocked)
    with pytest.raises(WorkspaceProviderError, match="termination is unknown"):
        provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    assert len(cancelled) == 2


def test_modal_termination_rpc_has_deadline_and_records_failure(remote, monkeypatch):
    provider, _, sandboxes, _ = remote
    if provider.name != "modal":
        pytest.skip("Modal-specific async SDK control plane")
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    import micro_eval.engine.providers.remote as remote_module
    monkeypatch.setattr(remote_module, "CONTROL_TIMEOUT_S", .02)
    cancelled = threading.Event()
    async def blocked(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(sandboxes[0].terminate, "aio", blocked)
    with pytest.raises(WorkspaceProviderError, match="termination failed"):
        provider.cleanup(handle)
    assert cancelled.is_set()
    assert handle.metadata["sandbox_cleanup"] == "failed"


def test_modal_execution_rpc_has_deadline(remote, monkeypatch):
    provider, _, sandboxes, _ = remote
    if provider.name != "modal":
        pytest.skip("Modal-specific async SDK control plane")
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    import micro_eval.engine.providers.remote as remote_module
    monkeypatch.setattr(remote_module, "CONTROL_TIMEOUT_S", .02)
    cancelled = threading.Event()
    async def blocked(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    monkeypatch.setattr(sandboxes[0].exec, "aio", blocked)
    with pytest.raises(TimeoutError):
        provider._run(sandboxes[0], ["true"], cap=100, timeout_s=.01)
    assert cancelled.is_set()
    provider.cleanup(handle)


def test_e2b_create_transport_loss_does_not_claim_cleanup(remote, monkeypatch):
    provider, _, sandboxes, _ = remote
    if provider.name != "e2b":
        pytest.skip("E2B-specific create control plane")
    def lost(**kwargs):
        raise TimeoutError("response unavailable")
    monkeypatch.setattr(sys.modules["e2b"].Sandbox, "create", lost)
    with pytest.raises(WorkspaceProviderError, match="allocation/termination is unknown"):
        provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    assert not sandboxes


@pytest.mark.parametrize("wrapper", ["prefix-{}", "{}-suffix", "Bearer {} trailing"])
def test_control_credential_substrings_cannot_enter_remote_environment(remote, wrapper):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    before = len(sandboxes[0].calls)
    secret = "control-e2b-key" if provider.name == "e2b" else "control-modal-secret"
    with pytest.raises(WorkspaceProviderError, match="credential value"):
        provider.exec_command(handle, ["true"], env={"COMPOSITE_VALUE": wrapper.format(secret)})
    assert len(sandboxes[0].calls) == before
    assert sandboxes[0].kills == 1


def test_long_unicode_inventory_is_bounded_before_sdk_receives_it(remote, tmp_path):
    provider, _, sandboxes, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    output = provider.prepare_output(handle, tmp_path / "download")
    # 3,000 legal names exceed 1 MiB after ensure_ascii JSON escaping, even
    # though each filename occupies fewer than 255 filesystem bytes.
    for index in range(3000):
        (output / (("界" * 70) + f"-{index:04d}")).touch()
    listing = provider._files(handle, {"op": "list", "path": str(output)})
    envelope = json.dumps({"ok": True, "value": listing}, ensure_ascii=True).encode() + b"\n"
    assert len(envelope) <= 512 * 1024
    assert listing["skipped"] is True
    assert 0 < len(listing["entries"]) < 3000
    assert sandboxes[0].kills == 0
    assert provider.exec_command(handle, ["true"]).exit_code == 0
    provider.cleanup(handle)


def test_large_stdin_is_removed_before_early_exit_response(remote):
    provider, _, _, _ = remote
    handle = provider.create(WorkspaceSpec(), cell_id="cell", run_id="run")
    result = asyncio.run(provider.execute(handle, ExecutionRequest(
        ["python3", "-c", "raise SystemExit(0)"], stdin=b"x" * 300000,
        timeout_s=10, output_cap_bytes=100)))
    assert result.exit_code == 0
    # A second sandbox command observes cleanup, rather than inspecting the
    # fake's host filesystem or relying on eventual whole-sandbox destruction.
    observed = provider.exec_command(handle, ["python3", "-c",
        "from pathlib import Path;assert not list(Path('.').glob('.micro-eval-input-*'));print('clean')"])
    assert observed.exit_code == 0
    assert observed.stdout == "clean\n"
    provider.cleanup(handle)
