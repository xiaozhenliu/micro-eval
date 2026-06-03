"""Release version consistency checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

from micro_eval import __version__
from micro_eval.config.loader import load_config, load_task_paths
from micro_eval.config.planner import build_run_plan

FIXTURES = Path(__file__).parent.parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]


def test_release_version_sources_are_aligned() -> None:
    version = (ROOT / "VERSION").read_text().strip()
    pyproject = (ROOT / "pyproject.toml").read_text()
    package_json = json.loads((ROOT / "ui" / "package.json").read_text())
    package_lock = json.loads((ROOT / "ui" / "package-lock.json").read_text())

    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version)
    assert __version__ == version
    assert 'dynamic = ["version"]' in pyproject
    assert '[tool.hatch.version]' in pyproject
    assert 'path = "VERSION"' in pyproject
    assert package_json["version"] == version
    assert package_lock["version"] == version
    assert package_lock["packages"][""]["version"] == version


def test_replay_tool_version_uses_runtime_package_version() -> None:
    config_path = FIXTURES / "configs" / "eval_matrix.yaml"
    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)

    plan = build_run_plan(config, tasks)

    assert plan.replay_canonical is not None
    assert plan.replay_canonical.tool_version == __version__
