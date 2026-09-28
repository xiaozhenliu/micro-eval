"""CLI tests for `micro-eval config` (GRO-549).

Uses typer's CliRunner (no subprocess). Acceptance/regression coverage
written after the implementation was verified manually end-to-end via the
real CLI (no TDD, per CLAUDE.md).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from micro_eval.cli.main import app
from micro_eval.config.loader import load_config, load_task_paths

runner = CliRunner()


def _invoke(args: list[str], input_json: dict | None = None):
    stdin = json.dumps(input_json) if input_json is not None else None
    return runner.invoke(app, args, input=stdin)


def _config_payload(config_id: str = "baseline") -> dict:
    return {
        "id": config_id,
        "name": config_id,
        "agent": {"name": config_id, "command": ["cat"]},
    }


def _task_payload(task_id: str = "hello") -> dict:
    return {"id": task_id, "name": "Hello", "input_payload": "hi"}


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_blank_workspace(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    result = _invoke(["config", "show", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["configurations"] == []
    assert payload["tasks"] == []
    assert payload["warnings"] == []


def test_show_empty_configurations_list(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\nconfigurations: []\n")
    result = _invoke(["config", "show", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["configurations"] == []


def test_show_missing_eval_yaml_warns(tmp_path: Path) -> None:
    result = _invoke(["config", "show", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert any("eval.yaml" in w for w in payload["warnings"])


def test_show_corrupted_task_is_isolated(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text(
        "project_name: unnamed\ntasks:\n  - tasks/broken.yaml\n"
    )
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "broken.yaml").write_text("id: [unterminated\n")
    result = _invoke(["config", "show", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tasks"][0]["task"] is None
    assert payload["tasks"][0]["error"]
    assert str(tmp_path) not in payload["tasks"][0]["error"]


def test_show_task_traversal_path_is_error_entry_not_crash(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text('project_name: unnamed\ntasks:\n  - "../outside.yaml"\n')
    result = _invoke(["config", "show", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tasks"][0]["task"] is None
    assert payload["tasks"][0]["error"]


# ---------------------------------------------------------------------------
# set-configuration / remove-configuration
# ---------------------------------------------------------------------------


def test_set_configuration_round_trips_with_loader(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    result = _invoke(["config", "set-configuration", "--project", str(tmp_path)], _config_payload())
    assert result.exit_code == 0, result.output

    config_path = tmp_path / "eval.yaml"
    # No tasks yet: load_config alone must still succeed (it does not require tasks).
    project = load_config(config_path)
    assert [c.id for c in project.configurations] == ["baseline"]


def test_set_configuration_and_task_are_loadable_together(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    assert _invoke(["config", "set-configuration", "--project", str(tmp_path)], _config_payload()).exit_code == 0
    assert _invoke(["config", "set-task", "--project", str(tmp_path)], _task_payload()).exit_code == 0

    config_path = tmp_path / "eval.yaml"
    project = load_config(config_path)
    tasks = load_task_paths(config_path, project)
    assert [t.id for t in tasks] == ["hello"]


def test_set_configuration_same_id_updates_not_duplicates(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    _invoke(["config", "set-configuration", "--project", str(tmp_path)], _config_payload())
    payload2 = _config_payload()
    payload2["name"] = "renamed"
    result = _invoke(["config", "set-configuration", "--project", str(tmp_path)], payload2)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["configurations"]) == 1
    assert payload["configurations"][0]["name"] == "renamed"


def test_set_configuration_preserves_other_top_level_keys(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\nguardrails:\n  max_concurrency: 7\n")
    result = _invoke(["config", "set-configuration", "--project", str(tmp_path)], _config_payload())
    assert result.exit_code == 0, result.output
    content = (tmp_path / "eval.yaml").read_text()
    assert "max_concurrency: 7" in content


def test_remove_configuration_removes_entry(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    _invoke(["config", "set-configuration", "--project", str(tmp_path)], _config_payload())
    result = _invoke(["config", "remove-configuration", "--project", str(tmp_path), "--id", "baseline"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["configurations"] == []


def test_remove_configuration_not_found_exits_1(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\nconfigurations: []\n")
    result = _invoke(["config", "remove-configuration", "--project", str(tmp_path), "--id", "nope"])
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]


# ---------------------------------------------------------------------------
# set-task / remove-task
# ---------------------------------------------------------------------------


def test_set_task_writes_literal_block_style_and_updates_tasks(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    payload = _task_payload()
    payload["input_payload"] = "line one\nline two"
    result = _invoke(["config", "set-task", "--project", str(tmp_path)], payload)
    assert result.exit_code == 0, result.output

    task_file = tmp_path / "tasks" / "hello.yaml"
    assert task_file.exists()
    content = task_file.read_text()
    assert "|" in content
    assert "line one" in content and "line two" in content
    assert "tasks/hello.yaml" in (tmp_path / "eval.yaml").read_text()


def test_remove_task_deletes_file_and_entry(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    _invoke(["config", "set-task", "--project", str(tmp_path)], _task_payload())
    result = _invoke(["config", "remove-task", "--project", str(tmp_path), "--id", "hello"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "tasks" / "hello.yaml").exists()
    payload = json.loads(result.output)
    assert payload["tasks"] == []


def test_set_task_seeds_legacy_tasks_dir_on_first_switch(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks_dir: mytasks\n")
    legacy_dir = tmp_path / "mytasks"
    legacy_dir.mkdir()
    (legacy_dir / "legacy1.yaml").write_text('id: legacy1\nname: L\ninput_payload: "hi"\n')

    result = _invoke(["config", "set-task", "--project", str(tmp_path)], _task_payload("newtask"))
    assert result.exit_code == 0, result.output
    content = (tmp_path / "eval.yaml").read_text()
    assert "mytasks/legacy1.yaml" in content
    assert "tasks/newtask.yaml" in content


# ---------------------------------------------------------------------------
# Negative tests: all exit 1, eval.yaml unchanged
# ---------------------------------------------------------------------------


@pytest.fixture()
def blank_project(tmp_path: Path) -> Path:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    return tmp_path


def test_set_configuration_stdin_not_json_exits_1(blank_project: Path) -> None:
    before = (blank_project / "eval.yaml").read_text()
    result = runner.invoke(
        app, ["config", "set-configuration", "--project", str(blank_project)], input="not json"
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]
    assert (blank_project / "eval.yaml").read_text() == before


def test_set_configuration_missing_required_field_exits_1(blank_project: Path) -> None:
    before = (blank_project / "eval.yaml").read_text()
    result = _invoke(
        ["config", "set-configuration", "--project", str(blank_project)],
        {"id": "x", "name": "x"},  # missing agent
    )
    assert result.exit_code == 1
    assert (blank_project / "eval.yaml").read_text() == before


def test_set_configuration_bad_secret_prefix_exits_1(blank_project: Path) -> None:
    before = (blank_project / "eval.yaml").read_text()
    payload = _config_payload()
    payload["agent"]["required_secrets"] = ["BAD_NAME"]
    result = _invoke(["config", "set-configuration", "--project", str(blank_project)], payload)
    assert result.exit_code == 1
    assert (blank_project / "eval.yaml").read_text() == before


def test_set_configuration_id_dotdot_exits_1(blank_project: Path) -> None:
    before = (blank_project / "eval.yaml").read_text()
    result = _invoke(["config", "set-configuration", "--project", str(blank_project)], _config_payload(".."))
    assert result.exit_code == 1
    assert (blank_project / "eval.yaml").read_text() == before


def test_set_configuration_id_with_slash_exits_1(blank_project: Path) -> None:
    before = (blank_project / "eval.yaml").read_text()
    result = _invoke(["config", "set-configuration", "--project", str(blank_project)], _config_payload("a/b"))
    assert result.exit_code == 1
    assert (blank_project / "eval.yaml").read_text() == before


def test_set_task_empty_input_payload_exits_1(blank_project: Path) -> None:
    """The editor rejects a blank prompt (the zod side does too), so the CLI
    and the browser agree instead of one accepting what the other refuses."""
    before = (blank_project / "eval.yaml").read_text()
    payload = _task_payload()
    payload["input_payload"] = ""
    result = _invoke(["config", "set-task", "--project", str(blank_project)], payload)
    assert result.exit_code == 1
    error = json.loads(result.output)
    assert error["kind"] == "validation"
    assert "input_payload" in error["error"]
    assert not (blank_project / "tasks").exists()
    assert (blank_project / "eval.yaml").read_text() == before


def test_error_json_carries_kind_and_no_absolute_path(blank_project: Path) -> None:
    result = _invoke(["config", "remove-configuration", "--project", str(blank_project), "--id", "nope"])
    assert result.exit_code == 1
    error = json.loads(result.output)
    assert error["kind"] == "not_found"
    assert str(blank_project) not in error["error"]


def test_set_configuration_secret_prefixed_env_key_exits_1(blank_project: Path) -> None:
    before = (blank_project / "eval.yaml").read_text()
    payload = _config_payload()
    payload["agent"]["env"] = {"MICRO_EVAL_SECRET_TOKEN": "value"}
    result = _invoke(["config", "set-configuration", "--project", str(blank_project)], payload)
    assert result.exit_code == 1
    assert json.loads(result.output)["kind"] == "validation"
    assert (blank_project / "eval.yaml").read_text() == before


def test_show_hardlinked_task_file_is_error_entry(blank_project: Path) -> None:
    (blank_project / "eval.yaml").write_text("project_name: unnamed\ntasks:\n  - tasks/leak.yaml\n")
    (blank_project / "tasks").mkdir()
    real = blank_project / "real.yaml"
    real.write_text('id: leak\nname: L\ninput_payload: "outside"\n')
    os.link(real, blank_project / "tasks" / "leak.yaml")
    result = _invoke(["config", "show", "--project", str(blank_project)])
    assert result.exit_code == 0, result.output
    entry = json.loads(result.output)["tasks"][0]
    assert entry["task"] is None
    assert "hard link" in entry["error"]


def test_remove_task_by_path_removes_unparseable_entry(blank_project: Path) -> None:
    (blank_project / "eval.yaml").write_text("project_name: unnamed\ntasks:\n  - tasks/broken.yaml\n")
    (blank_project / "tasks").mkdir()
    (blank_project / "tasks" / "broken.yaml").write_text("id: [unterminated\n")
    result = _invoke(["config", "remove-task", "--project", str(blank_project), "--path", "tasks/broken.yaml"])
    assert result.exit_code == 0, result.output
    assert not (blank_project / "tasks" / "broken.yaml").exists()
    assert json.loads(result.output)["tasks"] == []


def test_remove_task_requires_exactly_one_selector(blank_project: Path) -> None:
    result = _invoke(["config", "remove-task", "--project", str(blank_project)])
    assert result.exit_code == 1
    assert json.loads(result.output)["kind"] == "validation"


def test_show_empty_tasks_list_mirrors_loader_fallback(blank_project: Path) -> None:
    (blank_project / "eval.yaml").write_text("project_name: unnamed\ntasks: []\n")
    (blank_project / "tasks").mkdir()
    (blank_project / "tasks" / "legacy.yaml").write_text('id: legacy\nname: L\ninput_payload: "hi"\n')
    result = _invoke(["config", "show", "--project", str(blank_project)])
    assert result.exit_code == 0, result.output
    assert [entry["path"] for entry in json.loads(result.output)["tasks"]] == ["tasks/legacy.yaml"]


def test_eval_yaml_symlink_pointing_outside_project_exits_1(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    real = outside / "real.yaml"
    real.write_text("project_name: outside\n")
    (tmp_path / "eval.yaml").symlink_to(real)

    result = _invoke(["config", "set-configuration", "--project", str(tmp_path)], _config_payload())
    assert result.exit_code == 1
    assert real.read_text() == "project_name: outside\n"


def test_task_file_preexisting_symlink_exits_1(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    outside = tmp_path_factory.mktemp("outside")
    outside_file = outside / "secret.yaml"
    outside_file.write_text("")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "hello.yaml").symlink_to(outside_file)

    result = _invoke(["config", "set-task", "--project", str(tmp_path)], _task_payload())
    assert result.exit_code == 1
    assert outside_file.read_text() == ""


def test_show_raw_and_set_raw_round_trip_preserving_comments(blank_project: Path) -> None:
    content = "# comment survives\nproject_name: raw\n"
    result = _invoke(["config", "set-raw", "--project", str(blank_project)], {"content": content})
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"saved": True}
    shown = _invoke(["config", "show-raw", "--project", str(blank_project)])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output) == {"content": content, "redacted": False}


def test_set_raw_rejects_absolute_task_path_with_validation_kind(blank_project: Path) -> None:
    before = (blank_project / "eval.yaml").read_text()
    result = _invoke(["config", "set-raw", "--project", str(blank_project)], {"content": "project_name: x\ntasks:\n  - /tmp/x.yaml\n"})
    assert result.exit_code == 1
    error = json.loads(result.output)
    assert error["kind"] == "validation"
    assert "tasks[0]" in error["error"]
    assert (blank_project / "eval.yaml").read_text() == before


def test_active_workspace_only_refuses_archived_workspace_under_lock(tmp_path):
    # Round-11 review: the write holds workspace.lock and checks status inside it.
    import json as _json

    from micro_eval.server.workspace import WorkspaceManager

    data_root = tmp_path / "data"
    data_root.mkdir()
    manager = WorkspaceManager(data_root)
    ws = manager.create(name="a", owner="alice")
    ws_dir = manager.workspaces_dir / ws.workspace_id
    payload = _json.dumps({"id": "cfg", "name": "cfg", "agent": {"name": "a", "command": ["cat"]}})

    ok = runner.invoke(
        app,
        ["config", "set-configuration", "--project", str(ws_dir), "--member", "alice", "--active-workspace-only"],
        input=payload,
    )
    assert ok.exit_code == 0, ok.output

    manager.update(ws.workspace_id, status="archived")
    refused = runner.invoke(
        app,
        ["config", "set-configuration", "--project", str(ws_dir), "--member", "alice", "--active-workspace-only"],
        input=_json.dumps({"id": "cfg2", "name": "cfg2", "agent": {"name": "a", "command": ["cat"]}}),
    )
    assert refused.exit_code == 1
    err = _json.loads(refused.output.strip().splitlines()[-1])
    assert err["kind"] == "conflict"
    assert "read-only" in err["error"]
    assert "cfg2" not in (ws_dir / "eval.yaml").read_text()
