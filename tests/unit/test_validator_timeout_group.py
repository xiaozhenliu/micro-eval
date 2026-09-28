"""A timed-out validation command must not leave its children running
(round-5 review, 2026-09-12): the validator starts the command in its own
session and kills the whole process group on timeout."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from micro_eval.engine.adapter import Redactor
from micro_eval.evaluation.validator import _run_validation_command
from micro_eval.models.task import ExpectationSpec

GRANDCHILD = (
    "import subprocess, sys, time, pathlib\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "pathlib.Path('grandchild.pid').write_text(str(child.pid))\n"
    "time.sleep(60)\n"
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.timeout(30)
async def test_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    expectation = ExpectationSpec(type="command", command=[sys.executable, "-c", GRANDCHILD], timeout_s=2)

    passed, summary = await _run_validation_command(expectation, workspace, output_dir, Redactor({}))

    assert passed is False
    assert "timed out" in summary
    pid_file = workspace / "grandchild.pid"
    assert pid_file.exists(), "command did not start its child in time"
    grandchild = int(pid_file.read_text())
    for _ in range(20):  # the kill is delivered asynchronously; allow a moment
        if not _alive(grandchild):
            break
        time.sleep(0.1)
    assert not _alive(grandchild), "grandchild survived the timeout"
