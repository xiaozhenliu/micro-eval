"""Agent bridge unit tests."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from micro_eval.engine.agent_bridge import BridgeError, SubprocessBridge
from micro_eval.models.configuration import AgentSpec


def _echo_agent_spec() -> AgentSpec:
    """An agent that reads JSONL from stdin and echoes each turn back."""
    script = (
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    data = json.loads(line)\n"
        "    resp = {'turn': data['turn'], 'content': f\"echo: {data['content']}\"}\n"
        "    print(json.dumps(resp), flush=True)\n"
    )
    return AgentSpec(name="echo-agent", command=[sys.executable, "-c", script])


@pytest.mark.asyncio
async def test_subprocess_bridge_multi_turn(tmp_path: Path) -> None:
    bridge = SubprocessBridge(
        agent=_echo_agent_spec(),
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        turn_timeout_s=5.0,
    )
    await bridge.start()
    r1 = await bridge.send_turn("hello")
    assert "echo: hello" in r1
    r2 = await bridge.send_turn("world")
    assert "echo: world" in r2
    assert bridge.turn_count == 2
    exit_code, stderr = await bridge.stop()
    assert exit_code == 0


@pytest.mark.asyncio
async def test_subprocess_bridge_timeout(tmp_path: Path) -> None:
    agent = AgentSpec(name="slow", command=[sys.executable, "-c", "import time; time.sleep(60)"])
    bridge = SubprocessBridge(
        agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=0.1,
    )
    await bridge.start()
    with pytest.raises(BridgeError, match="timed out"):
        await bridge.send_turn("hello")
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_not_started() -> None:
    agent = AgentSpec(name="x", command=["true"])
    bridge = SubprocessBridge(agent=agent, cwd=Path("."), env={})
    with pytest.raises(BridgeError, match="not started"):
        await bridge.send_turn("hello")


@pytest.mark.asyncio
async def test_subprocess_bridge_process_crash(tmp_path: Path) -> None:
    """Agent exits after first turn — second turn should raise BridgeError."""
    script = (
        "import json, sys\n"
        "line = sys.stdin.readline()\n"
        "data = json.loads(line)\n"
        "print(json.dumps({'content': 'bye'}), flush=True)\n"
        "sys.exit(0)\n"
    )
    agent = AgentSpec(name="crash", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=2.0)
    await bridge.start()
    r1 = await bridge.send_turn("first")
    assert "bye" in r1
    with pytest.raises(BridgeError):
        await bridge.send_turn("second")
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_invalid_json(tmp_path: Path) -> None:
    """Agent returns non-JSON — should raise BridgeError."""
    script = (
        "import sys\n"
        "for line in sys.stdin:\n"
        "    print('this is not json', flush=True)\n"
    )
    agent = AgentSpec(name="bad-json", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=2.0)
    await bridge.start()
    with pytest.raises(BridgeError, match="invalid JSON"):
        await bridge.send_turn("hello")
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_missing_content_field(tmp_path: Path) -> None:
    """Agent returns JSON without content/text field — should return empty string."""
    script = (
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    print(json.dumps({'status': 'ok'}), flush=True)\n"
    )
    agent = AgentSpec(name="no-content", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, turn_timeout_s=2.0)
    await bridge.start()
    result = await bridge.send_turn("hello")
    assert result == ""
    await bridge.stop()


@pytest.mark.asyncio
async def test_subprocess_bridge_stop_already_exited(tmp_path: Path) -> None:
    """stop() on a process that already exited should not raise."""
    script = "import sys; sys.exit(0)"
    agent = AgentSpec(name="fast-exit", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"})
    await bridge.start()
    await asyncio.sleep(0.2)
    exit_code, stderr = await bridge.stop()
    assert exit_code == 0


@pytest.mark.asyncio
async def test_subprocess_bridge_stop_forceful_kill(tmp_path: Path) -> None:
    """Process that ignores SIGTERM should be killed via SIGKILL."""
    script = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True: time.sleep(1)\n"
    )
    agent = AgentSpec(name="unkillable", command=[sys.executable, "-c", script])
    bridge = SubprocessBridge(agent=agent, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"})
    await bridge.start()
    exit_code, stderr = await bridge.stop()
    assert exit_code != 0 or exit_code is None
