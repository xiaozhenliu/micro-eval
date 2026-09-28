"""Unit tests for micro_eval.config.editor (GRO-549, hardened after the
2026-09-12 external review: fd-based O_NOFOLLOW access, hardlink rejection,
validated task paths, loader-consistent `tasks:` semantics, secret checks).

Acceptance/regression coverage written after the implementation was verified
manually end-to-end (no TDD, per CLAUDE.md).
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pytest

from micro_eval.config.editor import (
    ConfigEditError,
    ConfigNotFoundError,
    build_project_draft,
    dump_yaml,
    is_safe_id,
    load_raw_eval_yaml,
    read_project_file,
    remove_configuration,
    remove_task,
    resolve_project_dir,
    set_task,
    strip_schema_version,
    upsert_configuration,
    validate_relative_path,
    write_project_file,
)

LONG_SECRET = "sk-test-secret-value-0123456789abcdef"

# ---------------------------------------------------------------------------
# is_safe_id / validate_relative_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["baseline", "a.b-c_d:e", "v1"])
def test_is_safe_id_accepts_safe_values(value: str) -> None:
    assert is_safe_id(value) is True


@pytest.mark.parametrize("value", [".", "..", "...", "a/b", "", "a b", None, 3])
def test_is_safe_id_rejects_unsafe_values(value: object) -> None:
    assert is_safe_id(value) is False


@pytest.mark.parametrize("value", ["tasks/x.yaml", "mytasks/sub/x.yaml", "x.yaml"])
def test_validate_relative_path_accepts(value: str) -> None:
    assert validate_relative_path(value) == PurePosixPath(value)


@pytest.mark.parametrize(
    "value",
    ["/etc/passwd", "../x.yaml", "tasks/../x.yaml", "tasks/./x.yaml", "C:x.yaml", "a\\b.yaml", "a\x00b", "", None, "a\nb"],
)
def test_validate_relative_path_rejects(value: object) -> None:
    with pytest.raises(ConfigEditError):
        validate_relative_path(value)


# ---------------------------------------------------------------------------
# strip_schema_version / dump_yaml / resolve_project_dir
# ---------------------------------------------------------------------------


def test_strip_schema_version_recursive() -> None:
    data = {
        "schema_version": "1.0",
        "id": "x",
        "nested": {"schema_version": "1.0", "value": 1},
        "items": [{"schema_version": "1.0", "n": 1}, {"n": 2}],
    }
    result = strip_schema_version(data)
    assert "schema_version" not in result
    assert "schema_version" not in result["nested"]
    assert all("schema_version" not in item for item in result["items"])


def test_dump_yaml_uses_literal_block_style_for_multiline_strings() -> None:
    text = dump_yaml({"input_payload": "line one\nline two"})
    assert "|" in text
    assert "line one" in text and "line two" in text


def test_dump_yaml_plain_style_for_single_line_strings() -> None:
    assert dump_yaml({"name": "baseline"}).strip() == "name: baseline"


def test_resolve_project_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        resolve_project_dir(tmp_path / "does-not-exist")


def test_resolve_project_dir_not_a_directory_raises(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")
    with pytest.raises(ConfigEditError):
        resolve_project_dir(file_path)


def test_resolve_project_dir_valid(tmp_path: Path) -> None:
    assert resolve_project_dir(tmp_path) == tmp_path.resolve()


# ---------------------------------------------------------------------------
# write_project_file / read_project_file safety
# ---------------------------------------------------------------------------


def _project(tmp_path: Path) -> Path:
    return tmp_path.resolve()


def test_write_rejects_existing_symlink_target(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    outside_file = outside / "real.yaml"
    outside_file.write_text("original")
    (tmp_path / "eval.yaml").symlink_to(outside_file)

    with pytest.raises(ConfigEditError):
        write_project_file(_project(tmp_path), PurePosixPath("eval.yaml"), "new content")
    assert outside_file.read_text() == "original"


def test_write_rejects_symlinked_parent_dir(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (tmp_path / "tasks").symlink_to(outside)

    with pytest.raises(ConfigEditError):
        write_project_file(_project(tmp_path), PurePosixPath("tasks/hello.yaml"), "content")
    assert list(outside.iterdir()) == []


def test_write_rejects_hardlinked_target(tmp_path: Path) -> None:
    real = tmp_path / "real.yaml"
    real.write_text("original")
    os.link(real, tmp_path / "eval.yaml")

    with pytest.raises(ConfigEditError):
        write_project_file(_project(tmp_path), PurePosixPath("eval.yaml"), "new")
    assert real.read_text() == "original"


def test_write_creates_dirs_and_replaces_without_leftovers(tmp_path: Path) -> None:
    project = _project(tmp_path)
    write_project_file(project, PurePosixPath("tasks/hello.yaml"), "first")
    assert (tmp_path / "tasks" / "hello.yaml").read_text() == "first"
    write_project_file(project, PurePosixPath("tasks/hello.yaml"), "second")
    assert (tmp_path / "tasks" / "hello.yaml").read_text() == "second"
    assert sorted(p.name for p in (tmp_path / "tasks").iterdir()) == ["hello.yaml"]


def test_read_rejects_symlink(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    real = outside / "real.yaml"
    real.write_text("secret: yes\n")
    (tmp_path / "eval.yaml").symlink_to(real)
    with pytest.raises(ConfigEditError):
        read_project_file(_project(tmp_path), PurePosixPath("eval.yaml"))


def test_read_rejects_hardlink(tmp_path: Path) -> None:
    real = tmp_path / "real.yaml"
    real.write_text("secret: yes\n")
    os.link(real, tmp_path / "eval.yaml")
    with pytest.raises(ConfigEditError):
        read_project_file(_project(tmp_path), PurePosixPath("eval.yaml"))


def test_read_missing_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError):
        read_project_file(_project(tmp_path), PurePosixPath("eval.yaml"))


# ---------------------------------------------------------------------------
# load_raw_eval_yaml
# ---------------------------------------------------------------------------


def test_load_raw_eval_yaml_missing_returns_empty(tmp_path: Path) -> None:
    assert load_raw_eval_yaml(_project(tmp_path)) == {}


def test_load_raw_eval_yaml_rejects_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text(": : : not yaml")
    with pytest.raises(ConfigEditError):
        load_raw_eval_yaml(_project(tmp_path))


def test_load_raw_eval_yaml_rejects_invalid_utf8(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_bytes(b"project_name: \xff\xfe\n")
    with pytest.raises(ConfigEditError):
        load_raw_eval_yaml(_project(tmp_path))


# ---------------------------------------------------------------------------
# build_project_draft (config show)
# ---------------------------------------------------------------------------


def test_build_project_draft_blank_workspace(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    draft = build_project_draft(_project(tmp_path))
    assert draft["project_name"] == "unnamed"
    assert draft["configurations"] == []
    assert draft["configuration_errors"] == []
    assert draft["tasks"] == []
    assert draft["warnings"] == []


def test_build_project_draft_missing_eval_yaml_warns(tmp_path: Path) -> None:
    draft = build_project_draft(_project(tmp_path))
    assert any("eval.yaml" in warning for warning in draft["warnings"])


def test_build_project_draft_invalid_utf8_eval_yaml_warns_not_crashes(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_bytes(b"project_name: \xff\n")
    draft = build_project_draft(_project(tmp_path))
    assert draft["configurations"] == []
    assert any("UTF-8" in warning for warning in draft["warnings"])


def test_build_project_draft_invalid_configuration_error_has_no_input_echo(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text(
        "project_name: unnamed\nconfigurations:\n  - id: bad\n    agent:\n      name: x\n      command: []\n      env:\n        TOKEN: super-secret-input-value\n"
    )
    draft = build_project_draft(_project(tmp_path))
    assert draft["configurations"] == []
    error = draft["configuration_errors"][0]
    assert error["id"] == "bad"
    assert "super-secret-input-value" not in error["error"]
    assert "input_value" not in error["error"]


def test_build_project_draft_corrupted_task_is_isolated(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks:\n  - tasks/broken.yaml\n  - tasks/ok.yaml\n")
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "broken.yaml").write_text("id: [unterminated\n")
    (tasks_dir / "ok.yaml").write_text('id: ok\nname: Ok\ninput_payload: "hi"\n')

    draft = build_project_draft(_project(tmp_path))
    by_path = {entry["path"]: entry for entry in draft["tasks"]}
    assert by_path["tasks/broken.yaml"]["task"] is None
    assert by_path["tasks/broken.yaml"]["error"]
    assert str(tmp_path) not in by_path["tasks/broken.yaml"]["error"]
    assert by_path["tasks/ok.yaml"]["task"]["id"] == "ok"


@pytest.mark.parametrize("entry", ["../outside.yaml", "/tmp/outside/secret.yaml", "a\\b.yaml"])
def test_build_project_draft_unsafe_task_entry_is_never_echoed(tmp_path: Path, entry: str) -> None:
    (tmp_path / "eval.yaml").write_text(f'project_name: unnamed\ntasks:\n  - "{entry}"\n')
    draft = build_project_draft(_project(tmp_path))
    assert draft["tasks"][0]["task"] is None
    assert draft["tasks"][0]["error"]
    assert draft["tasks"][0]["path"] == "<invalid tasks entry 0>"
    assert "outside" not in draft["tasks"][0]["path"]


def test_build_project_draft_absolute_tasks_dir_is_ignored_with_warning(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "leak.yaml").write_text('id: leak\nname: L\ninput_payload: "x"\n')
    (tmp_path / "eval.yaml").write_text(f"project_name: unnamed\ntasks_dir: {outside}\n")
    draft = build_project_draft(_project(tmp_path))
    assert draft["tasks"] == []
    assert any("tasks_dir" in warning for warning in draft["warnings"])
    assert all(str(outside) not in warning for warning in draft["warnings"])


def test_build_project_draft_legacy_tasks_dir_globbing(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "hello.yaml").write_text('id: hello\nname: Hello\ninput_payload: "hi"\n')
    draft = build_project_draft(_project(tmp_path))
    assert [entry["path"] for entry in draft["tasks"]] == ["tasks/hello.yaml"]


def test_build_project_draft_empty_tasks_list_falls_back_like_loader(tmp_path: Path) -> None:
    """The loader treats `tasks: []` like a missing key (glob tasks_dir); the
    draft must show the same task set `micro-eval run` would execute."""
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks: []\n")
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "legacy.yaml").write_text('id: legacy\nname: L\ninput_payload: "hi"\n')
    draft = build_project_draft(_project(tmp_path))
    assert [entry["path"] for entry in draft["tasks"]] == ["tasks/legacy.yaml"]


def test_build_project_draft_hardlinked_task_is_error_entry(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks:\n  - tasks/leak.yaml\n")
    (tmp_path / "tasks").mkdir()
    real = tmp_path / "real.yaml"
    real.write_text('id: leak\nname: L\ninput_payload: "outside content"\n')
    os.link(real, tmp_path / "tasks" / "leak.yaml")
    draft = build_project_draft(_project(tmp_path))
    assert draft["tasks"][0]["task"] is None
    assert "hard link" in draft["tasks"][0]["error"]


def test_build_project_draft_redacts_declared_secret_values_in_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_API_KEY", LONG_SECRET)
    (tmp_path / "eval.yaml").write_text(
        "project_name: unnamed\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n"
        f"      env:\n        TOKEN: {LONG_SECRET}\n        MICRO_EVAL_SECRET_OTHER: plain\n        SAFE: value\n"
    )
    draft = build_project_draft(_project(tmp_path))
    env = draft["configurations"][0]["agent"]["env"]
    assert LONG_SECRET not in env["TOKEN"]
    assert env["TOKEN"].startswith("[REDACTED")
    assert env["MICRO_EVAL_SECRET_OTHER"].startswith("[REDACTED")
    assert env["SAFE"] == "value"


# ---------------------------------------------------------------------------
# upsert_configuration / remove_configuration
# ---------------------------------------------------------------------------


def _agent_payload(config_id: str = "baseline", env: dict[str, str] | None = None) -> dict:
    return {
        "id": config_id,
        "name": config_id,
        "agent": {"name": config_id, "command": ["cat"], "env": env or {}},
    }


def test_upsert_configuration_creates_eval_yaml_when_missing(tmp_path: Path) -> None:
    upsert_configuration(_project(tmp_path), _agent_payload())
    draft = build_project_draft(_project(tmp_path))
    assert [c["id"] for c in draft["configurations"]] == ["baseline"]


def test_upsert_configuration_updates_in_place_not_duplicated(tmp_path: Path) -> None:
    project = _project(tmp_path)
    upsert_configuration(project, _agent_payload())
    payload2 = _agent_payload()
    payload2["name"] = "renamed"
    upsert_configuration(project, payload2)
    draft = build_project_draft(project)
    assert len(draft["configurations"]) == 1
    assert draft["configurations"][0]["name"] == "renamed"


def test_upsert_configuration_preserves_other_top_level_keys(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\nguardrails:\n  max_concurrency: 7\n")
    upsert_configuration(_project(tmp_path), _agent_payload())
    assert load_raw_eval_yaml(_project(tmp_path))["guardrails"]["max_concurrency"] == 7


def test_upsert_configuration_rejects_unsafe_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        upsert_configuration(_project(tmp_path), _agent_payload(".."))


def test_upsert_configuration_validation_error_has_no_input_echo(tmp_path: Path) -> None:
    payload = _agent_payload()
    payload["agent"]["required_secrets"] = ["NOT_PREFIXED_super-secret"]
    with pytest.raises(ConfigEditError) as excinfo:
        upsert_configuration(_project(tmp_path), payload)
    assert "super-secret" not in str(excinfo.value)
    assert excinfo.value.kind == "validation"


def test_upsert_configuration_rejects_secret_prefixed_env_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        upsert_configuration(_project(tmp_path), _agent_payload(env={"MICRO_EVAL_SECRET_X": "value"}))
    assert not (tmp_path / "eval.yaml").exists()


def test_upsert_configuration_rejects_env_value_equal_to_declared_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_API_KEY", LONG_SECRET)
    with pytest.raises(ConfigEditError):
        upsert_configuration(_project(tmp_path), _agent_payload(env={"TOKEN": LONG_SECRET}))
    assert not (tmp_path / "eval.yaml").exists()


def test_upsert_configuration_rejects_redaction_placeholder(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        upsert_configuration(_project(tmp_path), _agent_payload(env={"TOKEN": "[REDACTED:MICRO_EVAL_SECRET_X]"}))


def test_remove_configuration_not_found_is_not_found_kind(tmp_path: Path) -> None:
    upsert_configuration(_project(tmp_path), _agent_payload())
    with pytest.raises(ConfigNotFoundError) as excinfo:
        remove_configuration(_project(tmp_path), "nope")
    assert excinfo.value.kind == "not_found"


def test_remove_configuration_removes_entry(tmp_path: Path) -> None:
    upsert_configuration(_project(tmp_path), _agent_payload())
    remove_configuration(_project(tmp_path), "baseline")
    assert build_project_draft(_project(tmp_path))["configurations"] == []


# ---------------------------------------------------------------------------
# set_task / remove_task
# ---------------------------------------------------------------------------


def _task_payload(task_id: str = "hello") -> dict:
    return {"id": task_id, "name": "Hello", "input_payload": "hi"}


def test_set_task_writes_file_and_updates_tasks_list(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    set_task(_project(tmp_path), _task_payload())
    assert (tmp_path / "tasks" / "hello.yaml").exists()
    assert load_raw_eval_yaml(_project(tmp_path))["tasks"] == ["tasks/hello.yaml"]


def test_set_task_honours_custom_tasks_dir(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks_dir: mytasks\n")
    set_task(_project(tmp_path), _task_payload())
    assert (tmp_path / "mytasks" / "hello.yaml").exists()
    assert load_raw_eval_yaml(_project(tmp_path))["tasks"] == ["mytasks/hello.yaml"]


def test_set_task_multiline_prompt_uses_literal_block_style(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    payload = _task_payload()
    payload["input_payload"] = "first line\nsecond line"
    set_task(_project(tmp_path), payload)
    content = (tmp_path / "tasks" / "hello.yaml").read_text()
    assert "|" in content and "second line" in content


def test_set_task_same_id_updates_not_duplicates(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    project = _project(tmp_path)
    set_task(project, _task_payload())
    payload2 = _task_payload()
    payload2["name"] = "Renamed"
    set_task(project, payload2)
    assert load_raw_eval_yaml(project)["tasks"] == ["tasks/hello.yaml"]
    assert build_project_draft(project)["tasks"][0]["task"]["name"] == "Renamed"


@pytest.mark.parametrize("header", ["project_name: unnamed\ntasks_dir: mytasks\n", "project_name: unnamed\ntasks_dir: mytasks\ntasks: []\n"])
def test_set_task_seeds_legacy_globbed_files_when_switching_to_explicit_list(tmp_path: Path, header: str) -> None:
    (tmp_path / "eval.yaml").write_text(header)
    legacy_dir = tmp_path / "mytasks"
    legacy_dir.mkdir()
    (legacy_dir / "legacy1.yaml").write_text('id: legacy1\nname: L\ninput_payload: "hi"\n')

    set_task(_project(tmp_path), _task_payload("newtask"))

    assert load_raw_eval_yaml(_project(tmp_path))["tasks"] == ["mytasks/legacy1.yaml", "mytasks/newtask.yaml"]


def test_set_task_rejects_unsafe_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        set_task(_project(tmp_path), _task_payload(".."))


def test_set_task_rejects_blank_prompt(tmp_path: Path) -> None:
    payload = _task_payload()
    payload["input_payload"] = "   \n"
    with pytest.raises(ConfigEditError):
        set_task(_project(tmp_path), payload)
    assert not (tmp_path / "tasks").exists()


def test_set_task_rejects_preexisting_symlink_task_file(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    outside = tmp_path_factory.mktemp("outside")
    outside_file = outside / "secret.yaml"
    outside_file.write_text("")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "hello.yaml").symlink_to(outside_file)

    with pytest.raises(ConfigEditError):
        set_task(_project(tmp_path), _task_payload())
    assert outside_file.read_text() == ""


def test_remove_task_by_id_deletes_file_and_entry(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    project = _project(tmp_path)
    set_task(project, _task_payload())
    remove_task(project, task_id="hello")
    assert not (tmp_path / "tasks" / "hello.yaml").exists()
    assert load_raw_eval_yaml(project).get("tasks", []) == []


def test_remove_task_by_id_matches_file_content_not_file_name(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks:\n  - custom/first.yaml\n  - custom/second.yaml\n")
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "first.yaml").write_text('id: alpha\nname: A\ninput_payload: "x"\n')
    (custom / "second.yaml").write_text('id: beta\nname: B\ninput_payload: "y"\n')

    remove_task(_project(tmp_path), task_id="beta")

    assert (custom / "first.yaml").exists()
    assert not (custom / "second.yaml").exists()
    assert load_raw_eval_yaml(_project(tmp_path))["tasks"] == ["custom/first.yaml"]


def test_remove_task_by_path_removes_unparseable_entry(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks:\n  - tasks/broken.yaml\n")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "broken.yaml").write_text("id: [unterminated\n")

    remove_task(_project(tmp_path), path="tasks/broken.yaml")

    assert not (tmp_path / "tasks" / "broken.yaml").exists()
    assert load_raw_eval_yaml(_project(tmp_path))["tasks"] == []


def test_remove_task_by_path_rejects_paths_outside_the_task_set(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    (tmp_path / "notes.yaml").write_text("keep: me\n")
    with pytest.raises(ConfigNotFoundError):
        remove_task(_project(tmp_path), path="notes.yaml")
    assert (tmp_path / "notes.yaml").exists()
    with pytest.raises(ConfigEditError):
        remove_task(_project(tmp_path), path="../outside.yaml")


def test_remove_task_requires_exactly_one_selector(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        remove_task(_project(tmp_path))
    with pytest.raises(ConfigEditError):
        remove_task(_project(tmp_path), task_id="a", path="tasks/a.yaml")


def test_remove_task_not_found_raises_not_found(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    with pytest.raises(ConfigNotFoundError):
        remove_task(_project(tmp_path), task_id="nope")


# ---------------------------------------------------------------------------
# Round-2 review fixes: short secrets, tasks_dir edge cases, in-place task
# updates, raw (Advanced tab) read/write through the same safety layer
# ---------------------------------------------------------------------------

from micro_eval.config.editor import (  # noqa: E402  (grouped with the tests they serve)
    redact_env,
    set_raw_config,
    show_raw_config,
)
from micro_eval.models.ids import sha256_text  # noqa: E402


def test_redact_env_masks_short_declared_secret_by_exact_match() -> None:
    env = {"TOKEN": "abc", "OTHER": "abcdef", "CONTAINS": f"x{LONG_SECRET}y"}
    masked = redact_env(env, {"MICRO_EVAL_SECRET_SHORT": "abc", "MICRO_EVAL_SECRET_LONG": LONG_SECRET})
    assert masked["TOKEN"] == "[REDACTED:MICRO_EVAL_SECRET_SHORT]"
    assert masked["OTHER"] == "[REDACTED:MICRO_EVAL_SECRET_SHORT]def"  # substring masking at any length
    assert masked["CONTAINS"] == "x[REDACTED:MICRO_EVAL_SECRET_LONG]y"


def test_build_project_draft_symlinked_tasks_dir_is_warning_not_crash(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "leak.yaml").write_text('id: leak\nname: L\ninput_payload: "x"\n')
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    (tmp_path / "tasks").symlink_to(outside)
    draft = build_project_draft(_project(tmp_path))
    assert draft["tasks"] == []
    assert any("tasks_dir" in warning for warning in draft["warnings"])


def test_build_project_draft_null_tasks_dir_is_warning(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks_dir: null\n")
    draft = build_project_draft(_project(tmp_path))
    assert draft["tasks"] == []
    assert any("tasks_dir" in warning for warning in draft["warnings"])
    with pytest.raises(ConfigEditError):
        set_task(_project(tmp_path), _task_payload())


def test_set_task_updates_existing_custom_path_in_place(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\ntasks:\n  - custom/old.yaml\n")
    (tmp_path / "custom").mkdir()
    (tmp_path / "custom" / "old.yaml").write_text('id: hello\nname: Old\ninput_payload: "x"\n')

    payload = _task_payload("hello")
    payload["name"] = "New"
    set_task(_project(tmp_path), payload)

    assert not (tmp_path / "tasks").exists()
    assert "name: New" in (tmp_path / "custom" / "old.yaml").read_text()
    assert load_raw_eval_yaml(_project(tmp_path))["tasks"] == ["custom/old.yaml"]


def test_task_revision_id_matches_file_text_without_path_reread(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: unnamed\n")
    set_task(_project(tmp_path), _task_payload())
    text = (tmp_path / "tasks" / "hello.yaml").read_text()
    draft = build_project_draft(_project(tmp_path))
    assert draft["tasks"][0]["task"]["revision_id"] == sha256_text(text)


def test_show_raw_config_redacts_declared_secret_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_API_KEY", LONG_SECRET)
    (tmp_path / "eval.yaml").write_text(
        f"# keep me\nproject_name: unnamed\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n      env:\n        TOKEN: {LONG_SECRET}\n        WORD: unrelated\n"
    )
    result = show_raw_config(_project(tmp_path))
    assert result["redacted"] is True
    assert LONG_SECRET not in result["content"]
    assert "TOKEN: [REDACTED:MICRO_EVAL_SECRET_API_KEY]" in result["content"]
    assert "WORD: unrelated" in result["content"]
    assert "# keep me" in result["content"]


def test_show_raw_config_missing_file(tmp_path: Path) -> None:
    assert show_raw_config(_project(tmp_path)) == {"content": "", "redacted": False}


def test_set_raw_config_preserves_comments_and_validates(tmp_path: Path) -> None:
    content = "# my comment\nproject_name: raw\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\ntasks:\n  - tasks/x.yaml\n"
    set_raw_config(_project(tmp_path), content)
    assert (tmp_path / "eval.yaml").read_text() == content


@pytest.mark.parametrize(
    "content",
    [
        "project_name: x\ntasks:\n  - /etc/passwd\n",
        "project_name: x\ntasks:\n  - ../outside.yaml\n",
        "project_name: x\ntasks_dir: /tmp/outside\n",
        "project_name: x\noutput_dir: /tmp/out\n",
        "project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n      env:\n        MICRO_EVAL_SECRET_X: v\n",
        "project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n      env:\n        TOKEN: '[REDACTED:MICRO_EVAL_SECRET_X]'\n",
        "- not\n- a\n- mapping\n",
        "project_name: [unterminated\n",
    ],
)
def test_set_raw_config_rejects_unsafe_content(tmp_path: Path, content: str) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: before\n")
    with pytest.raises(ConfigEditError):
        set_raw_config(_project(tmp_path), content)
    assert (tmp_path / "eval.yaml").read_text() == "project_name: before\n"


def test_set_raw_config_rejects_oversize(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        set_raw_config(_project(tmp_path), "project_name: x\n# " + "a" * (1024 * 1024))


# ---------------------------------------------------------------------------
# Round-3 review fixes
# ---------------------------------------------------------------------------


def test_show_raw_config_refuses_escaped_secret_that_text_redaction_misses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "abc")
    (tmp_path / "eval.yaml").write_text(
        'project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n      env:\n        TOKEN: "\\x61\\x62\\x63"\n'
    )
    with pytest.raises(ConfigEditError) as excinfo:
        show_raw_config(_project(tmp_path))
    assert "cannot be redacted" in str(excinfo.value)


def test_show_raw_config_plain_secret_is_redacted_not_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", LONG_SECRET)
    (tmp_path / "eval.yaml").write_text(f"project_name: x\nnote: {LONG_SECRET}\n")
    result = show_raw_config(_project(tmp_path))
    assert result["redacted"] is True
    assert LONG_SECRET not in result["content"]


@pytest.mark.parametrize(
    "content",
    ["project_name: x\nconfigurations: null\n", "project_name: x\noutput_dir: null\n", "project_name: null\n", "project_name: x\ntasks: null\n"],
)
def test_set_raw_config_rejects_present_null_keys(tmp_path: Path, content: str) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: before\n")
    with pytest.raises(ConfigEditError):
        set_raw_config(_project(tmp_path), content)
    assert (tmp_path / "eval.yaml").read_text() == "project_name: before\n"


def test_set_raw_config_rejects_symlinked_tasks_dir_and_task_file(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "leak.yaml").write_text('id: leak\nname: L\ninput_payload: "x"\n')
    (tmp_path / "tasks").symlink_to(outside)
    with pytest.raises(ConfigEditError) as excinfo:
        set_raw_config(_project(tmp_path), "project_name: x\ntasks_dir: tasks\n")
    assert "tasks_dir" in str(excinfo.value)

    (tmp_path / "tasks").unlink()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "leak.yaml").symlink_to(outside / "leak.yaml")
    with pytest.raises(ConfigEditError) as excinfo:
        set_raw_config(_project(tmp_path), "project_name: x\ntasks:\n  - tasks/leak.yaml\n")
    assert "tasks[0]" in str(excinfo.value)
    assert not (tmp_path / "eval.yaml").exists()


def test_set_raw_config_accepts_references_that_do_not_exist_yet(tmp_path: Path) -> None:
    set_raw_config(_project(tmp_path), "project_name: x\ntasks:\n  - tasks/later.yaml\ntasks_dir: mytasks\n")
    assert (tmp_path / "eval.yaml").exists()


def test_upsert_configuration_preserves_stored_value_behind_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A legacy configuration whose env holds a declared secret shows the
    placeholder in the form; saving other fields must keep the stored value."""
    monkeypatch.setenv("MICRO_EVAL_SECRET_API_KEY", LONG_SECRET)
    (tmp_path / "eval.yaml").write_text(
        f"project_name: x\nconfigurations:\n  - id: a\n    name: old\n    agent:\n      name: a\n      command: [cat]\n      env:\n        TOKEN: {LONG_SECRET}\n"
    )
    payload = _agent_payload("a", env={"TOKEN": "[REDACTED:MICRO_EVAL_SECRET_API_KEY]"})
    payload["name"] = "renamed"
    upsert_configuration(_project(tmp_path), payload)
    raw = load_raw_eval_yaml(_project(tmp_path))
    assert raw["configurations"][0]["name"] == "renamed"
    assert raw["configurations"][0]["agent"]["env"]["TOKEN"] == LONG_SECRET


def test_upsert_configuration_placeholder_without_stored_value_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigEditError):
        upsert_configuration(_project(tmp_path), _agent_payload("a", env={"TOKEN": "[REDACTED:MICRO_EVAL_SECRET_X]"}))


def test_conversational_fields_round_trip_through_show(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: x\n")
    payload = _task_payload("chat")
    payload.update({"scenario": "user asks", "expected_outcome": "helpful answer", "user_description": "polite"})
    set_task(_project(tmp_path), payload)
    task = build_project_draft(_project(tmp_path))["tasks"][0]["task"]
    assert (task["scenario"], task["expected_outcome"], task["user_description"]) == ("user asks", "helpful answer", "polite")


# ---------------------------------------------------------------------------
# Round-4 review fixes
# ---------------------------------------------------------------------------


def test_show_raw_config_refuses_secret_hidden_in_mapping_key_or_short_substring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "abc")
    project = _project(tmp_path)
    (tmp_path / "eval.yaml").write_text('project_name: x\n"\\x61\\x62\\x63": value\n')
    with pytest.raises(ConfigEditError):
        show_raw_config(project)
    # A short secret inside a longer value is masked as a substring now.
    (tmp_path / "eval.yaml").write_text("project_name: x\nnote: xabcx\n")
    result = show_raw_config(project)
    assert "abc" not in result["content"]
    assert "x[REDACTED:MICRO_EVAL_SECRET_TOKEN]x" in result["content"]


def test_build_project_draft_redacts_secrets_outside_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_API_KEY", LONG_SECRET)
    (tmp_path / "eval.yaml").write_text(
        f"project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [curl, -H, 'Bearer {LONG_SECRET}']\ntasks:\n  - tasks/t.yaml\n"
    )
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.yaml").write_text(f'id: t\nname: T\ninput_payload: "use {LONG_SECRET} please"\n')
    draft = build_project_draft(_project(tmp_path))
    assert LONG_SECRET not in draft["configurations"][0]["agent"]["command"][2]
    assert LONG_SECRET not in draft["tasks"][0]["task"]["input_payload"]
    assert "[REDACTED:MICRO_EVAL_SECRET_API_KEY]" in draft["tasks"][0]["task"]["input_payload"]


def test_upsert_configuration_rejects_composite_placeholder_and_placeholder_outside_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_API_KEY", LONG_SECRET)
    (tmp_path / "eval.yaml").write_text(
        f"project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n      env:\n        TOKEN: pre-{LONG_SECRET}-post\n"
    )
    with pytest.raises(ConfigEditError):
        upsert_configuration(_project(tmp_path), _agent_payload("a", env={"TOKEN": "pre-[REDACTED:MICRO_EVAL_SECRET_API_KEY]-post"}))
    payload = _agent_payload("a")
    payload["agent"]["command"] = ["curl", "[REDACTED:MICRO_EVAL_SECRET_API_KEY]"]
    with pytest.raises(ConfigEditError):
        upsert_configuration(_project(tmp_path), payload)
    assert f"pre-{LONG_SECRET}-post" in (tmp_path / "eval.yaml").read_text()


def test_set_task_rejects_placeholder_anywhere(tmp_path: Path) -> None:
    payload = _task_payload()
    payload["input_payload"] = "call with [REDACTED:MICRO_EVAL_SECRET_X]"
    with pytest.raises(ConfigEditError):
        set_task(_project(tmp_path), payload)
    assert not (tmp_path / "tasks").exists()


# ---------------------------------------------------------------------------
# Round-5 review fixes
# ---------------------------------------------------------------------------

import threading  # noqa: E402


def test_build_project_draft_redacts_project_fields_error_ids_paths_and_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_API_KEY", LONG_SECRET)
    (tmp_path / "eval.yaml").write_text(
        f"project_name: proj-{LONG_SECRET}\ndescription: about {LONG_SECRET}\n"
        f"configurations:\n  - id: id-{LONG_SECRET}\n    name: n\n"  # invalid entry (no agent) -> error id
        f"  - id: ok\n    name: ok\n    agent:\n      name: ok\n      command: [cat]\n    parameters:\n      key-{LONG_SECRET}: v\n"
        f"tasks:\n  - tasks/{LONG_SECRET}.yaml\n"
    )
    draft = build_project_draft(_project(tmp_path))
    assert LONG_SECRET not in json_dumps(draft)


def json_dumps(value: object) -> str:
    import json

    return json.dumps(value)


def test_show_raw_config_refuses_short_secret_hidden_in_comment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_PIN", "abc")
    (tmp_path / "eval.yaml").write_text("# note xabcx\nproject_name: x\n")
    result = show_raw_config(_project(tmp_path))
    assert "abc" not in result["content"]
    assert "# note x[REDACTED:MICRO_EVAL_SECRET_PIN]x" in result["content"]


def test_legacy_layout_is_warned_in_show_and_refused_by_writers(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text(
        "project_name: old\nbaseline:\n  command: [cat]\ncandidate:\n  command: [cat]\n"
    )
    draft = build_project_draft(_project(tmp_path))
    assert draft["configurations"] == []
    assert any("legacy" in warning for warning in draft["warnings"])
    for action in (
        lambda: upsert_configuration(_project(tmp_path), _agent_payload()),
        lambda: set_task(_project(tmp_path), _task_payload()),
        lambda: remove_configuration(_project(tmp_path), "baseline"),
        lambda: remove_task(_project(tmp_path), task_id="x"),
    ):
        with pytest.raises(ConfigEditError, match="legacy"):
            action()
    assert "baseline:" in (tmp_path / "eval.yaml").read_text()


def test_concurrent_configuration_writes_are_serialised_by_the_project_lock(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text("project_name: race\n")
    project = _project(tmp_path)
    errors: list[BaseException] = []

    def writer(prefix: str) -> None:
        try:
            for index in range(15):
                upsert_configuration(project, _agent_payload(f"{prefix}-{index}"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(name,)) for name in ("a", "b", "c")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    ids = {c["id"] for c in build_project_draft(project)["configurations"]}
    assert len(ids) == 45


def test_draft_marks_non_list_tasks_field_as_invalid(tmp_path):
    # Round-9 review: the loader refuses `tasks: <string>`; the draft must not
    # silently fall back to tasks_dir and show a runnable project.
    from micro_eval.config.editor import build_project_draft

    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\ntasks: tasks/t.yaml\n")
    draft = build_project_draft(tmp_path)
    assert len(draft["tasks"]) == 1
    assert draft["tasks"][0]["error"] is not None
    assert "list" in draft["tasks"][0]["error"]


def test_writes_append_a_redacted_audit_line_with_the_member(tmp_path, monkeypatch):
    # Round-10 review: every browser-side write records who changed what.
    import json as _json

    from micro_eval.config.editor import build_project_draft, set_raw_config, upsert_configuration

    monkeypatch.setenv("MICRO_EVAL_SECRET_KEY", "alice-secret")
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")
    upsert_configuration(
        tmp_path,
        {"id": "cfg", "name": "cfg", "agent": {"name": "a", "command": ["cat"]}},
        member="alice-secret",
    )
    set_raw_config(tmp_path, "project_name: y\nconfigurations: []\n", member="bob")
    lines = [_json.loads(l) for l in (tmp_path / ".micro-eval" / "config-audit.jsonl").read_text().splitlines()]
    assert [(l["action"], l["target"]) for l in lines] == [("set-configuration", "cfg"), ("set-raw", "eval.yaml")]
    assert lines[0]["member"] == "[REDACTED:MICRO_EVAL_SECRET_KEY]"
    assert lines[1]["member"] == "bob"
    assert build_project_draft(tmp_path)["schema_version"] == "1.0"


def test_draft_marks_explicit_null_tasks_as_invalid(tmp_path):
    from micro_eval.config.editor import build_project_draft

    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.yaml").write_text('id: t\nname: T\ninput_payload: "x"\n')
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\ntasks: null\n")
    draft = build_project_draft(tmp_path)
    assert [entry["error"] is not None for entry in draft["tasks"]] == [True]


def test_set_raw_rejects_secret_in_legacy_agent_env(tmp_path, monkeypatch):
    from micro_eval.config.editor import set_raw_config

    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "sk-legacy")
    (tmp_path / "eval.yaml").write_text("project_name: x\n")
    legacy = (
        "project_name: x\nbaseline:\n  command: cat\n  env:\n    TOKEN: sk-legacy\n"
        "candidate:\n  command: cat\n"
    )
    with pytest.raises(ConfigEditError):
        set_raw_config(tmp_path, legacy)
    assert (tmp_path / "eval.yaml").read_text() == "project_name: x\n"


def test_broken_audit_target_refuses_the_write_before_changing_anything(tmp_path, tmp_path_factory):
    from micro_eval.config.editor import set_raw_config

    (tmp_path / "eval.yaml").write_text("project_name: before\n")
    (tmp_path / ".micro-eval").mkdir()
    outside = tmp_path_factory.mktemp("outside") / "audit.jsonl"
    (tmp_path / ".micro-eval" / "config-audit.jsonl").symlink_to(outside)
    with pytest.raises(ConfigEditError, match="audit"):
        set_raw_config(tmp_path, "project_name: after\n", member="alice")
    assert (tmp_path / "eval.yaml").read_text() == "project_name: before\n"
    assert not outside.exists()


def test_draft_schema_version_survives_a_secret_equal_to_it(tmp_path, monkeypatch):
    from micro_eval.config.editor import build_project_draft

    monkeypatch.setenv("MICRO_EVAL_SECRET_VERSION", "1.0")
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")
    assert build_project_draft(tmp_path)["schema_version"] == "1.0"


def test_audit_append_failure_rolls_the_write_back(tmp_path, monkeypatch):
    # Round-12 review: a change that cannot be audited must not persist.
    import errno
    import os as _os

    from micro_eval.config import editor as _editor

    (tmp_path / "eval.yaml").write_text("project_name: before\nconfigurations: []\n")
    real_write = _os.write

    def failing_write(fd, data):  # noqa: ANN001 - test stub
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(_editor.os, "write", failing_write)
    with pytest.raises(ConfigEditError, match="audit"):
        _editor.set_raw_config(tmp_path, "project_name: after\nconfigurations: []\n", member="alice")
    monkeypatch.setattr(_editor.os, "write", real_write)
    assert (tmp_path / "eval.yaml").read_text() == "project_name: before\nconfigurations: []\n"
    assert (tmp_path / ".micro-eval" / "config-audit.jsonl").read_text() == ""


def test_set_task_rolls_back_task_file_when_eval_yaml_write_fails(tmp_path, monkeypatch):
    from micro_eval.config import editor as _editor

    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")

    def boom(project_dir, raw):  # noqa: ANN001 - test stub
        raise ConfigEditError("disk full", kind="internal")

    monkeypatch.setattr(_editor, "_write_eval_yaml", boom)
    with pytest.raises(ConfigEditError, match="disk full"):
        _editor.set_task(tmp_path, {"id": "t1", "name": "T", "input_payload": "x"}, member="alice")
    assert not (tmp_path / "tasks" / "t1.yaml").exists()
    assert "t1" not in (tmp_path / "eval.yaml").read_text()
    assert (tmp_path / ".micro-eval" / "config-audit.jsonl").read_text() == ""


def test_remove_task_rolls_back_when_eval_yaml_write_fails(tmp_path, monkeypatch):
    from micro_eval.config import editor as _editor

    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")
    _editor.set_task(tmp_path, {"id": "t1", "name": "T", "input_payload": "x"}, member="alice")
    before = (tmp_path / "eval.yaml").read_text()

    def boom(project_dir, raw):  # noqa: ANN001 - test stub
        raise ConfigEditError("disk full", kind="internal")

    monkeypatch.setattr(_editor, "_write_eval_yaml", boom)
    with pytest.raises(ConfigEditError, match="disk full"):
        _editor.remove_task(tmp_path, task_id="t1", member="alice")
    assert (tmp_path / "tasks" / "t1.yaml").exists()
    assert (tmp_path / "eval.yaml").read_text() == before


@pytest.mark.parametrize("path", [".micro-eval/config-audit.jsonl", ".micro-eval/config.lock", ".micro-eval"])
def test_runtime_directory_is_reserved_for_task_paths(tmp_path, path):
    from micro_eval.config.editor import remove_task, set_raw_config, validate_relative_path

    with pytest.raises(ConfigEditError, match="runtime directory"):
        validate_relative_path(path)
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")
    with pytest.raises(ConfigEditError):
        set_raw_config(tmp_path, f"project_name: x\nconfigurations: []\ntasks:\n  - {path}\n")
    with pytest.raises(ConfigEditError):
        remove_task(tmp_path, path=path)


def test_output_dir_may_still_use_the_runtime_directory(tmp_path):
    from micro_eval.config.editor import set_raw_config

    (tmp_path / "eval.yaml").write_text("project_name: x\n")
    set_raw_config(tmp_path, "project_name: x\nconfigurations: []\noutput_dir: .micro-eval/runs\n")
    assert "output_dir: .micro-eval/runs" in (tmp_path / "eval.yaml").read_text()


def test_short_audit_write_is_truncated_back(tmp_path, monkeypatch):
    from micro_eval.config import editor as _editor

    (tmp_path / "eval.yaml").write_text("project_name: before\nconfigurations: []\n")
    real_write = _editor.os.write
    calls = {"n": 0}

    def short_then_fail(fd, data):  # noqa: ANN001 - test stub
        calls["n"] += 1
        if calls["n"] == 1:
            return real_write(fd, data[:5])
        raise OSError("boom")

    monkeypatch.setattr(_editor.os, "write", short_then_fail)
    with pytest.raises(ConfigEditError, match="audit"):
        _editor.set_raw_config(tmp_path, "project_name: after\nconfigurations: []\n", member="alice")
    monkeypatch.setattr(_editor.os, "write", real_write)
    assert (tmp_path / ".micro-eval" / "config-audit.jsonl").read_bytes() == b""
    assert (tmp_path / "eval.yaml").read_text() == "project_name: before\nconfigurations: []\n"


def test_set_task_rejects_declared_secret_values_anywhere(tmp_path, monkeypatch):
    from micro_eval.config.editor import set_task

    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "sk-task-leak")
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")
    with pytest.raises(ConfigEditError, match="MICRO_EVAL_SECRET_TOKEN"):
        set_task(tmp_path, {"id": "t", "name": "T", "input_payload": "use sk-task-leak please"})
    with pytest.raises(ConfigEditError, match="MICRO_EVAL_SECRET_TOKEN"):
        set_task(tmp_path, {"id": "t", "name": "T", "input_payload": "x", "tags": ["sk-task-leak"]})
    assert not (tmp_path / "tasks").exists()


def test_upsert_configuration_rejects_declared_secret_in_command(tmp_path, monkeypatch):
    from micro_eval.config.editor import upsert_configuration

    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "sk-cfg-leak")
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")
    with pytest.raises(ConfigEditError, match="MICRO_EVAL_SECRET_TOKEN"):
        upsert_configuration(
            tmp_path, {"id": "c", "name": "c", "agent": {"name": "a", "command": ["curl", "-H", "Bearer sk-cfg-leak"]}}
        )
    assert "sk-cfg-leak" not in (tmp_path / "eval.yaml").read_text()


def test_unknown_expectation_fields_survive_the_draft(tmp_path):
    from micro_eval.config.editor import build_project_draft, set_task

    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\n")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.yaml").write_text(
        'id: t\nname: T\ninput_payload: "x"\nexpectations:\n  - type: regex_match\n    pattern: "^x$"\n    flags: [i]\n'
    )
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\ntasks:\n  - tasks/t.yaml\n")
    draft = build_project_draft(tmp_path)
    exp = draft["tasks"][0]["task"]["expectations"][0]
    assert exp["type"] == "regex_match" and exp["pattern"] == "^x$" and exp["flags"] == ["i"]
    # Round trip through set_task keeps them too.
    set_task(tmp_path, {**draft["tasks"][0]["task"], "name": "T2"})
    assert 'pattern: ^x$' in (tmp_path / "tasks" / "t.yaml").read_text()


@pytest.mark.parametrize(
    "content",
    [
        "project_name: sk-raw-leak\nconfigurations: []\n",
        "# note: sk-raw-leak\nproject_name: x\nconfigurations: []\n",
        "project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [curl, sk-raw-leak]\n",
        "project_name: x\nconfigurations: []\nsk-raw-leak: 1\n",
    ],
)
def test_set_raw_rejects_declared_secret_anywhere_in_the_text(tmp_path, monkeypatch, content):
    from micro_eval.config.editor import set_raw_config

    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "sk-raw-leak")
    (tmp_path / "eval.yaml").write_text("project_name: before\n")
    with pytest.raises(ConfigEditError, match="MICRO_EVAL_SECRET_TOKEN"):
        set_raw_config(tmp_path, content, member="alice")
    assert (tmp_path / "eval.yaml").read_text() == "project_name: before\n"


def test_set_raw_rejects_yaml_escaped_declared_secret(tmp_path, monkeypatch):
    from micro_eval.config.editor import set_raw_config

    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", 'a"b')
    (tmp_path / "eval.yaml").write_text("project_name: before\n")
    escaped = 'project_name: "a\\u0022b"\nconfigurations: []\n'
    with pytest.raises(ConfigEditError, match="MICRO_EVAL_SECRET_TOKEN"):
        set_raw_config(tmp_path, escaped, member="alice")
    assert (tmp_path / "eval.yaml").read_text() == "project_name: before\n"


def test_fifo_task_file_is_refused_without_blocking(tmp_path):
    import os as _os
    import threading

    from micro_eval.config.editor import build_project_draft

    (tmp_path / "tasks").mkdir()
    _os.mkfifo(tmp_path / "tasks" / "t.yaml")
    (tmp_path / "eval.yaml").write_text("project_name: x\nconfigurations: []\ntasks:\n  - tasks/t.yaml\n")
    box = {}
    thread = threading.Thread(target=lambda: box.update(draft=build_project_draft(tmp_path)), daemon=True)
    thread.start()
    thread.join(5.0)
    assert not thread.is_alive(), "draft build blocked on the FIFO"
    assert box["draft"]["tasks"][0]["error"] is not None
