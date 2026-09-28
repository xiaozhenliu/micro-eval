"""Real OS enforcement from the cell entry point (GRO-993).

Ordinary unsupported hosts skip with a concrete reason. The dedicated CI jobs
set MICRO_EVAL_REQUIRE_OS_POLICY=1, turning unavailable policy into a failure.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import socket
import sys
from pathlib import Path

import pytest

from micro_eval.config.planner import build_run_plan
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.engine.providers.os_policy import BubblewrapProvider, SeatbeltProvider
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, Guardrails, ProjectConfigV2
from micro_eval.models.ids import safe_path_segment
from micro_eval.models.task import ExpectationSpec, TaskSpec, WorkspaceSpec


@pytest.fixture
def os_provider(tmp_path):
    required = os.environ.get("MICRO_EVAL_REQUIRE_OS_POLICY") == "1"
    provider_cls = {"Darwin": SeatbeltProvider, "Linux": BubblewrapProvider}.get(platform.system())
    if provider_cls is None or shutil.which(provider_cls.executable) is None:
        reason = f"OS policy unavailable: {platform.system()} lacks the required sandbox executable"
        if required:
            pytest.fail(reason)
        pytest.skip(reason)
    provider = provider_cls(tmp_path)
    handle = provider.create(WorkspaceSpec(network_policy="none"), cell_id="availability", run_id="probe")
    try:
        result = provider.exec_command(handle, [sys.executable, "-c", "print('policy-ready')"])
    finally:
        provider.cleanup(handle)
    if result.exit_code or result.stdout.strip() != "policy-ready":
        reason = f"{provider.name} runtime probe failed: {result.stderr}"
        if required:
            pytest.fail(reason)
        pytest.skip(reason)
    expected = os.environ.get("MICRO_EVAL_EXPECT_OS_PROVIDER")
    assert expected is None or expected == provider.name
    print(f"Real policy provider: {provider.name}; Python: {sys.executable}")
    return provider.name


@pytest.fixture
def listener():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(16)
        yield server.getsockname()[1]


def _config(command, *, output_mode="stdout"):
    config = ProjectConfigV2(
        project_name="os-policy-cell-probe",
        configurations=[ConfigurationSpec(id="probe", name="probe", agent=AgentSpec(
            name="probe", command=command, output_mode=output_mode,
        ))],
        guardrails=Guardrails(max_concurrency=1),
    )
    config.config_hash = "os-policy-cell-probe"
    return config


def _network_code(port, connected):
    return f"""
import socket
try:
    connection = socket.create_connection(("127.0.0.1", {port}), timeout=1)
except OSError:
    connected = False
else:
    connection.close()
    connected = True
assert connected is {connected!r}, ("network policy mismatch", connected)
"""


def _stage_command(stage, targets, port, *, connected):
    prior = {"setup": [], "agent": ["setup"], "validator": ["setup", "agent"]}[stage]
    code = f"""
from pathlib import Path
import os
for prior in {prior!r}:
    assert Path(prior + "-proof.txt").read_text() == "inside-and-boundaries-passed"
for target in {list(map(str, targets))!r}:
    try:
        Path(target).write_text("unauthorized-write")
    except OSError:
        pass
    else:
        raise AssertionError("write outside cell succeeded: " + target)
"""
    code += _network_code(port, connected)
    code += f"\nPath({stage!r} + '-proof.txt').write_text('inside-and-boundaries-passed')\n"
    if stage == "agent":
        code += "Path(os.environ['MICRO_EVAL_OUTPUT_FILE']).write_text('setup-agent-output-passed')\n"
        code += "Path('nested').mkdir(); Path('nested/value.txt').write_text('nested-cwd')\n"
    return ["{python}", "-c", code]


@pytest.mark.parametrize("policy", ["full", "none"])
def test_cell_setup_agent_validator_enforce_write_and_network_policy(tmp_path, os_provider, listener, policy):
    # Build first to seed a real sibling workspace and paths inside this run.
    task = TaskSpec(id="probe", name="Probe", input_payload="", workspace=WorkspaceSpec(
        isolation_level="os_policy", network_policy=policy,
    ))
    plan = build_run_plan(_config(["{python}", "-c", "pass"], output_mode="file"), [task], project_root=tmp_path)
    workspace_parent = tmp_path / ".micro-eval" / "workspaces" / safe_path_segment(plan.run_id)
    sibling = workspace_parent / "other-cell" / "sentinel.txt"
    outside = tmp_path / "outside-sentinel.txt"
    run_dir = tmp_path / ".micro-eval" / "runs" / plan.run_id
    guarded_metadata = run_dir / "guarded-metadata.json"
    targets = [outside, sibling, guarded_metadata, run_dir / "run.json", run_dir / "manifest.json"]
    for target in (outside, sibling, guarded_metadata):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("untouched")
    setup = _stage_command("setup", targets, listener, connected=policy == "full")
    agent = _stage_command("agent", targets, listener, connected=policy == "full")
    validator = _stage_command("validator", targets, listener, connected=policy == "full")
    plan.cells[0].task.workspace.setup = [setup]
    plan.cells[0].task.expectations = [
        ExpectationSpec(type="command", command=validator),
        ExpectationSpec(type="command", cwd="nested", command=[
            "{python}", "-c", "from pathlib import Path; assert Path('value.txt').read_text() == 'nested-cwd'",
        ]),
        ExpectationSpec(type="command", cwd="{output_dir}", command=[
            "{python}", "-c", "from pathlib import Path; assert Path('output.txt').read_text() == 'setup-agent-output-passed'",
        ]),
    ]
    plan.cells[0].configuration.agent.command = agent
    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    result = record.results[0]
    assert result.status.value == "pass", result.model_dump()
    assert result.output_summary == "setup-agent-output-passed"
    assert result.cell_snapshot.setup_exit_code == 0
    assert record.evaluations and all(evaluation.pass_fail == "pass" for evaluation in record.evaluations)
    assert result.cell_snapshot.cleanup_status == "cleaned"
    assert not Path(result.cell_snapshot.workspace_path).exists()
    assert not list(workspace_parent.glob(".micro-eval-io-*"))
    assert all(target.read_text() == "untouched" for target in (outside, sibling, guarded_metadata))
    assert not any("os_policy unavailable" in caveat for caveat in result.snapshot_gate_result.caveats)
    print(f"{os_provider}/{policy}: setup, agent and validator each denied 5 external writes; network checked")


def test_logical_localhost_positive_control(tmp_path, listener):
    command = ["{python}", "-c", _network_code(listener, True) + "\nprint('reachable')"]
    task = TaskSpec(id="logical", name="Logical positive control", input_payload="", workspace=WorkspaceSpec())
    plan = build_run_plan(_config(command), [task], project_root=tmp_path)
    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    assert record.results[0].status.value == "pass", record.results[0].model_dump()
    assert record.results[0].output_summary.strip() == "reachable"
