"""Execution-layer architectural contracts (issue #5).

Two contracts that the engine must honour and that no schema/golden test covers:

1. kernel-must-use-adapter: the run kernel orchestrates; it must delegate all
   agent process spawning to AgentAdapter and never spawn subprocesses itself.
2. timeout escalation: a timed-out agent is first sent SIGTERM (terminate) and,
   only if it does not exit within the grace window, SIGKILL (kill).

The shell-injection grep gate in CI covers `shell=True`/`create_subprocess_shell`;
these tests cover the orthogonal "go through the adapter" and "escalate cleanly"
guarantees with executable assertions.
"""

from __future__ import annotations

import asyncio.subprocess
import sys
from pathlib import Path

import pytest

from micro_eval.engine.adapter import AgentAdapter
from micro_eval.models.configuration import AgentSpec
from micro_eval.models.run import CellStatus

ENGINE_DIR = Path(__file__).resolve().parents[2] / "src" / "micro_eval" / "engine"

# Patterns that spawn an OS process. The kernel must use none of them directly.
FORBIDDEN_SPAWN_PATTERNS = (
    "create_subprocess_exec",
    "create_subprocess_shell",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_",
    "os.system",
    "os.popen",
    "os.exec",
    "os.spawn",
)


# ---------------------------------------------------------------------------
# Contract 1: kernel-must-use-adapter
# ---------------------------------------------------------------------------


def test_kernel_does_not_spawn_subprocesses_directly() -> None:
    """The kernel must route agent execution through the adapter, not spawn itself."""
    source = (ENGINE_DIR / "kernel.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN_SPAWN_PATTERNS if pattern in source]
    assert offenders == [], (
        f"kernel.py spawns processes directly ({offenders}); all agent execution "
        "must go through AgentAdapter.invoke."
    )
    # Positive side of the contract: the kernel actually calls the adapter.
    assert "adapter.invoke" in source, "kernel.py must invoke the adapter"


# adapter.py is the canonical agent spawner. runner.py is the legacy AgentRunner
# (AgentConfig-based) still pending retirement (#3); it is the only sanctioned
# exception. Any *new* engine module that spawns async subprocesses is a
# contract violation — agent execution belongs in the adapter.
SANCTIONED_SPAWNERS = {"adapter.py", "runner.py"}


def test_only_the_adapter_spawns_agent_subprocesses_in_engine() -> None:
    """No new engine module may spawn async subprocesses outside the adapter."""
    for path in ENGINE_DIR.glob("*.py"):
        if path.name in SANCTIONED_SPAWNERS:
            continue
        source = path.read_text(encoding="utf-8")
        assert "create_subprocess_exec" not in source and "create_subprocess_shell" not in source, (
            f"{path.name} spawns async subprocesses; agent execution must go through AgentAdapter"
        )


# ---------------------------------------------------------------------------
# Contract 2: timeout -> terminate -> kill escalation
# ---------------------------------------------------------------------------


def _agent(command: list[str], *, timeout_s: float) -> AgentSpec:
    return AgentSpec(name="timeout-agent", command=command, timeout_s=timeout_s)


def _spy_signals(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record terminate()/kill() calls on the asyncio subprocess transport."""
    calls: list[str] = []
    proc_cls = asyncio.subprocess.Process
    orig_terminate = proc_cls.terminate
    orig_kill = proc_cls.kill

    def rec_terminate(self):  # type: ignore[no-untyped-def]
        calls.append("terminate")
        return orig_terminate(self)

    def rec_kill(self):  # type: ignore[no-untyped-def]
        calls.append("kill")
        return orig_kill(self)

    monkeypatch.setattr(proc_cls, "terminate", rec_terminate)
    monkeypatch.setattr(proc_cls, "kill", rec_kill)
    return calls


async def test_timeout_terminates_a_responsive_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process that respects SIGTERM is terminated and never escalated to kill."""
    calls = _spy_signals(monkeypatch)
    adapter = AgentAdapter()
    agent = _agent([sys.executable, "-c", "import time; time.sleep(30)"], timeout_s=0.4)

    result, _ = await adapter.invoke(
        agent=agent, input_payload="", cwd=tmp_path, output_dir=tmp_path / "out"
    )

    assert result.status == CellStatus.timeout
    assert result.timed_out is True
    assert calls == ["terminate"], f"expected terminate only, got {calls}"


async def test_timeout_escalates_to_kill_when_sigterm_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process that ignores SIGTERM is escalated to SIGKILL after the grace window."""
    calls = _spy_signals(monkeypatch)
    adapter = AgentAdapter()
    script = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
    agent = _agent([sys.executable, "-c", script], timeout_s=0.4)

    result, _ = await adapter.invoke(
        agent=agent, input_payload="", cwd=tmp_path, output_dir=tmp_path / "out"
    )

    assert result.status == CellStatus.timeout
    assert result.timed_out is True
    assert calls == ["terminate", "kill"], f"expected terminate then kill, got {calls}"
