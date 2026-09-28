"""The run-time loader must not follow symlinks or multi-link files for task
inputs (round-4 review, 2026-09-12): a task file or tasks directory that
points outside the project would otherwise be read at run time even though
the browser-side editor refused to write it."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from micro_eval.config.loader import ConfigError, load_config, load_task, load_task_paths, load_tasks

TASK = 'id: t\nname: T\ninput_payload: "x"\n'


def test_load_task_rejects_symlinked_file(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "leak.yaml"
    outside.write_text(TASK)
    link = tmp_path / "t.yaml"
    link.symlink_to(outside)
    with pytest.raises(ConfigError, match="symlink"):
        load_task(link)


def test_load_task_rejects_hardlinked_file(tmp_path: Path) -> None:
    real = tmp_path / "real.yaml"
    real.write_text(TASK)
    os.link(real, tmp_path / "t.yaml")
    with pytest.raises(ConfigError, match="hard links"):
        load_task(tmp_path / "t.yaml")


def test_load_tasks_rejects_symlinked_directory(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "leak.yaml").write_text(TASK)
    (tmp_path / "tasks").symlink_to(outside)
    with pytest.raises(ConfigError, match="symlink"):
        load_tasks(tmp_path / "tasks")


def test_load_tasks_rejects_symlinked_entry_inside_directory(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "leak.yaml"
    outside.write_text(TASK)
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "ok.yaml").write_text(TASK)
    (tmp_path / "tasks" / "leak.yaml").symlink_to(outside)
    with pytest.raises(ConfigError, match="symlink"):
        load_tasks(tmp_path / "tasks")


def test_load_tasks_plain_files_still_load(tmp_path: Path) -> None:
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "ok.yaml").write_text(TASK)
    assert [task.id for task in load_tasks(tmp_path / "tasks")] == ["t"]


def test_load_task_paths_rejects_traversal_and_intermediate_symlink(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    from micro_eval.config.loader import load_config, load_task_paths

    outside = tmp_path_factory.mktemp("outside")
    (outside / "leak.yaml").write_text(TASK)
    config_path = tmp_path / "eval.yaml"
    base_cfg = "project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n"

    config_path.write_text(base_cfg + "tasks:\n  - ../outside/leak.yaml\n")
    with pytest.raises(ConfigError, match="relative path"):
        load_task_paths(config_path, load_config(config_path), strict_paths=True)

    (tmp_path / "linked").symlink_to(outside)
    config_path.write_text(base_cfg + "tasks:\n  - linked/leak.yaml\n")
    with pytest.raises(ConfigError, match="symlink"):
        load_task_paths(config_path, load_config(config_path))

    config_path.write_text(base_cfg + "tasks_dir: linked\n")
    with pytest.raises(ConfigError, match="symlink"):
        load_task_paths(config_path, load_config(config_path))


def test_load_task_paths_allows_parent_reference_without_strict(tmp_path: Path) -> None:
    """Local layouts (config in a subdirectory, tasks beside it) keep working."""
    from micro_eval.config.loader import load_config, load_task_paths

    (tmp_path / "configs").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.yaml").write_text(TASK)
    config_path = tmp_path / "configs" / "eval.yaml"
    config_path.write_text(
        "project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\ntasks:\n  - ../tasks/t.yaml\n"
    )
    assert [t.id for t in load_task_paths(config_path, load_config(config_path))] == ["t"]


def test_build_plan_strict_paths_refuses_parent_reference(tmp_path: Path) -> None:
    """The Team Server calls `build-plan --strict-paths`; a hand-edited
    `../x.yaml` reference must fail there even though local layouts allow it."""
    from typer.testing import CliRunner

    from micro_eval.cli.main import app

    (tmp_path / "ws").mkdir()
    (tmp_path / "leak.yaml").write_text(TASK)
    (tmp_path / "ws" / "eval.yaml").write_text(
        "project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\ntasks:\n  - ../leak.yaml\n"
    )
    runner = CliRunner()
    strict = runner.invoke(app, ["build-plan", "--workspace", str(tmp_path / "ws"), "--strict-paths"])
    assert strict.exit_code == 1
    assert "relative path" in strict.output
    lenient = runner.invoke(app, ["build-plan", "--workspace", str(tmp_path / "ws")])
    assert lenient.exit_code == 0


CONFIG = "project_name: x\nconfigurations:\n  - id: a\n    name: a\n    agent:\n      name: a\n      command: [cat]\n"


def test_strict_load_config_rejects_symlinked_eval_yaml(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    # Round-7 review: the file is opened with O_NOFOLLOW, so a symlink is
    # refused by the open itself rather than by a check that runs earlier.
    outside = tmp_path_factory.mktemp("outside") / "eval.yaml"
    outside.write_text(CONFIG)
    link = tmp_path / "eval.yaml"
    link.symlink_to(outside)
    with pytest.raises(ConfigError, match="plain file"):
        load_config(link, strict_paths=True)
    # Local projects (non-strict) keep following symlinks.
    assert load_config(link).project_name == "x"


def test_strict_load_config_rejects_hardlinked_eval_yaml(tmp_path: Path) -> None:
    real = tmp_path / "real.yaml"
    real.write_text(CONFIG)
    os.link(real, tmp_path / "eval.yaml")
    with pytest.raises(ConfigError, match="plain file"):
        load_config(tmp_path / "eval.yaml", strict_paths=True)


def test_strict_load_config_reads_plain_file(tmp_path: Path) -> None:
    (tmp_path / "eval.yaml").write_text(CONFIG)
    assert load_config(tmp_path / "eval.yaml", strict_paths=True).project_name == "x"


def _strict_project(tmp_path: Path, tasks_line: str) -> Path:
    (tmp_path / "eval.yaml").write_text(CONFIG + tasks_line)
    return tmp_path / "eval.yaml"


def test_strict_task_paths_refuse_symlinked_intermediate_directory(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    # Round-8 review: every component is opened via dir_fd + O_NOFOLLOW, so
    # a `tasks/` directory that is a symlink cannot reach an outside file.
    outside = tmp_path_factory.mktemp("outside")
    (outside / "t.yaml").write_text(TASK)
    (tmp_path / "tasks").symlink_to(outside)
    config_path = _strict_project(tmp_path, "tasks:\n  - tasks/t.yaml\n")
    project = load_config(config_path, strict_paths=True)
    with pytest.raises(ConfigError, match="symlink"):
        load_task_paths(config_path, project, strict_paths=True)


def test_strict_tasks_dir_skips_nothing_but_refuses_symlinked_entries(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "leak.yaml"
    outside.write_text(TASK)
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "a.yaml").write_text(TASK)
    (tmp_path / "tasks" / "b.yaml").symlink_to(outside)
    config_path = _strict_project(tmp_path, "tasks_dir: tasks\n")
    project = load_config(config_path, strict_paths=True)
    with pytest.raises(ConfigError, match="plain file"):
        load_task_paths(config_path, project, strict_paths=True)


def test_strict_task_revision_hashes_the_bytes_that_were_parsed(tmp_path: Path) -> None:
    import hashlib

    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.yaml").write_text(TASK)
    config_path = _strict_project(tmp_path, "tasks:\n  - tasks/t.yaml\n")
    project = load_config(config_path, strict_paths=True)
    [task] = load_task_paths(config_path, project, strict_paths=True)
    assert task.revision_id == hashlib.sha256(TASK.encode()).hexdigest()
    assert task.id == "t"


def test_strict_task_paths_refuse_dot_segments(tmp_path: Path) -> None:
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "t.yaml").write_text(TASK)
    config_path = _strict_project(tmp_path, "tasks:\n  - ./tasks/t.yaml\n")
    project = load_config(config_path, strict_paths=True)
    with pytest.raises(ConfigError, match="relative path inside"):
        load_task_paths(config_path, project, strict_paths=True)
