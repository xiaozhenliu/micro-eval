"""Opt-in cloud probes; default CI never allocates paid remote resources.

Run with MICRO_EVAL_RUN_REMOTE_LIVE=1, the provider-specific
MICRO_EVAL_SECRET_* credentials, and the matching micro-eval extra installed.
No LLM endpoint is called. These probes supplement offline contracts; they do
not certify arbitrary hostile-code isolation or every network destination.
"""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path

import pytest

from micro_eval.config.planner import build_run_plan
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.engine.providers.base import ExecutionRequest, ProviderRegistry
from micro_eval.engine.providers.remote import E2BProvider, ModalProvider
from micro_eval.engine.workspace import WorkspaceManager
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, OutputMode, ProjectConfigV2
from micro_eval.models.task import WorkspaceSpec, TaskSpec


@pytest.fixture(params=[E2BProvider, ModalProvider], ids=["e2b", "modal"])
def live_provider(request, tmp_path):
    if os.environ.get("MICRO_EVAL_RUN_REMOTE_LIVE") != "1":
        pytest.skip("remote live probes require explicit MICRO_EVAL_RUN_REMOTE_LIVE=1")
    provider = request.param(tmp_path)
    if not provider.supported_levels:
        pytest.skip(f"{provider.name} control credentials are not configured")
    return provider


@pytest.mark.asyncio
async def test_remote_live_cell_upload_setup_agent_validator_download_cleanup(
    live_provider, tmp_path: Path, monkeypatch, record_property,
):
    provider = live_provider
    record_property("provider", provider.name)
    record_property("sdk_version", importlib.metadata.version(provider.name))
    (tmp_path / "fixture.txt").write_text("uploaded fixture")
    handles = []
    original_create = provider.create
    def create(*args, **kwargs):
        handle = original_create(*args, **kwargs)
        handles.append(handle)
        record_property("sandbox_id", handle.metadata["sandbox_id"])
        return handle
    monkeypatch.setattr(provider, "create", create)
    original_init = WorkspaceManager.__init__
    def init(manager, *args, **kwargs):
        original_init(manager, *args, **kwargs)
        manager._registry = ProviderRegistry()
        manager._registry.register(provider)
    monkeypatch.setattr(WorkspaceManager, "__init__", init)
    code = """from pathlib import Path
import socket, sys
assert Path('fixture.txt').read_text() == 'uploaded fixture'
assert Path('setup.txt').read_text() == 'setup complete'
try:
    connection = socket.create_connection(('1.1.1.1', 443), timeout=2)
except OSError:
    pass
else:
    connection.close()
    raise AssertionError('network=none permitted public egress')
Path('agent.txt').write_text('agent complete')
Path(sys.argv[1]).write_text('remote answer')
print(sys.version)
"""
    config = ProjectConfigV2(project_name="remote-live-probe", configurations=[ConfigurationSpec(
        id="remote", name="Remote", agent=AgentSpec(name="probe", command=["{python}", "-c", code,
            "{output_file}"], output_mode=OutputMode.file, timeout_s=30),
    )])
    config.config_hash = "remote-live-probe"
    task = TaskSpec(id="live", name="Remote live lifecycle", input_payload="probe", workspace=WorkspaceSpec(
        type="files", files=["fixture.txt"], isolation_level=provider.level, network_policy="none",
        setup=[["python3", "-c", "from pathlib import Path;Path('setup.txt').write_text('setup complete')"]],
    ), expectations=[{"type": "command", "command": ["python3", "-c",
        "from pathlib import Path;assert Path('agent.txt').read_text()=='agent complete'"]}])
    record = await ExecutionKernel(tmp_path).run(build_run_plan(config, [task], project_root=tmp_path))
    result = record.results[0]
    assert result.status.value == "pass", result.stderr_summary
    assert result.cell_snapshot.cleanup_status == "cleaned"
    assert len(handles) == 1
    assert handles[0].metadata["sandbox_cleanup"] == "confirmed"
    record_property("remote_runtime", result.stdout_summary)
    record_property("sandbox_cleanup", handles[0].metadata["sandbox_cleanup"])
    # The adapter's selected output must have crossed the remote-to-host boundary.
    assert any(path.read_text() == "remote answer" for path in tmp_path.rglob("output.txt"))


@pytest.mark.asyncio
async def test_remote_live_deadline_confirms_whole_sandbox_termination(live_provider, record_property):
    provider = live_provider
    handle = provider.create(WorkspaceSpec(network_policy="none"), cell_id="timeout-probe", run_id="live")
    record_property("provider", provider.name)
    record_property("sandbox_id", handle.metadata["sandbox_id"])
    try:
        result = await provider.execute(handle, ExecutionRequest(
            ["python3", "-c", "import time;time.sleep(120)"], timeout_s=2, output_cap_bytes=1024))
        assert result.timed_out
        assert handle.metadata["sandbox_cleanup"] == "confirmed"
        record_property("sandbox_cleanup", handle.metadata["sandbox_cleanup"])
    finally:
        provider.cleanup(handle)
