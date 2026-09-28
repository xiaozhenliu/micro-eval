"""Agent timeouts terminate descendants in the adapter-owned process group."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from micro_eval.engine.adapter import AgentAdapter
from micro_eval.engine.providers.base import IsolationLevel, WorkspaceHandle
from micro_eval.engine.workspace import WorkspaceManager
from micro_eval.models.configuration import AgentSpec
from micro_eval.models.run import CellStatus
from micro_eval.models.task import WorkspaceSpec, WorkspaceType


GRANDCHILD = (
    "import pathlib, signal, subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', "
    "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)'])\n"
    "pathlib.Path('grandchild.pid').write_text(str(child.pid))\n"
    "time.sleep(300)\n"
)


def _running(pid: int) -> bool:
    """A zombie has stopped executing even if its parent has not reaped it."""
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists() and stat_path.read_text().split(") ", 1)[1].startswith("Z"):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.timeout(30)
async def test_timeout_kills_grandchild_that_ignores_sigterm(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    agent = AgentSpec(name="timeout-agent", command=[sys.executable, "-c", GRANDCHILD], timeout_s=1)

    result, _ = await AgentAdapter().invoke(
        agent=agent,
        input_payload="",
        cwd=workspace,
        output_dir=tmp_path / "out",
    )

    assert result.status == CellStatus.timeout
    pid_file = workspace / "grandchild.pid"
    assert pid_file.exists(), "agent did not spawn its grandchild before timeout"
    grandchild = int(pid_file.read_text())
    try:
        for _ in range(20):
            if not _running(grandchild):
                break
            await asyncio.sleep(0.1)
        assert not _running(grandchild), "grandchild survived the adapter timeout"
    finally:
        if _running(grandchild):
            os.kill(grandchild, signal.SIGKILL)


@pytest.mark.parametrize(
    ("provider_name", "level", "expected"),
    [
        ("seatbelt", IsolationLevel.os_policy, (
            "applies OS policy to setup, agent and command validation",
            "host-readable files are not confidential", "owned process group",
        )),
        ("bubblewrap", IsolationLevel.os_policy, (
            "applies OS policy to setup, agent and command validation",
            "host-readable files are not confidential", "owned process group",
        )),
        ("e2b", IsolationLevel.vm, (
            "dedicated remote sandbox", "SDK contract tests do not prove cloud",
            "remote workspace observation is unavailable",
        )),
        ("modal", IsolationLevel.container, (
            "dedicated remote sandbox", "SDK contract tests do not prove cloud",
            "remote workspace observation is unavailable",
        )),
    ],
)
def test_workspace_records_provider_timeout_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    level: IsolationLevel,
    expected: tuple[str, ...],
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class Provider:
        def create(self, spec: WorkspaceSpec, *, cell_id: str, run_id: str) -> WorkspaceHandle:
            return WorkspaceHandle(
                workspace_path=workspace,
                provider_name=provider_name,
                isolation_level=level,
                workspace_type=WorkspaceType.blank,
            )

    manager = WorkspaceManager(tmp_path)
    monkeypatch.setattr(manager.registry, "select", lambda requested: Provider())
    caveats: list[str] = []

    manager.prepare(
        cell_id="caveat-cell",
        workspace=WorkspaceSpec(type=WorkspaceType.blank, isolation_level=level),
        caveats=caveats,
    )

    assert any(
        provider_name in caveat and all(fragment in caveat for fragment in expected)
        for caveat in caveats
    )
