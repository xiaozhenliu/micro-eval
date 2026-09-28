"""Tests for the bundled starter-tasks template content (GRO-554).

Covers: each task YAML loads as a valid TaskSpec, the template's eval.yaml
(with a configuration injected, since the shipped template intentionally
ships `configurations: []`) resolves all 5 tasks via load_task_paths, the
digest stored in each task YAML matches the shipped `tests/` directory, and
the package-side judge (`python -m micro_eval.tools.verify_protected`)
judges buggy vs. fixed vs. tampered-tests correctly in an isolated copy.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from micro_eval.config.loader import load_config, load_task, load_task_paths
from micro_eval.tools.verify_protected import compute_protected_digest

TEMPLATE_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "micro_eval"
    / "server"
    / "seed_templates"
    / "starter-tasks"
)
SOLUTIONS_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "starter_tasks_solutions"

TASK_IDS = [
    "date-range-overlap",
    "csv-quoted-fields",
    "lru-cache-order",
    "slugify-hyphens",
    "page-bounds",
]

TASK_MODULES = {
    "date-range-overlap": "date_range_overlap.py",
    "csv-quoted-fields": "csv_quoted_fields.py",
    "lru-cache-order": "lru_cache_order.py",
    "slugify-hyphens": "slugify_hyphens.py",
    "page-bounds": "page_bounds.py",
}


def _expected_digest(task_id: str) -> str:
    task = load_task(TEMPLATE_DIR / "tasks" / f"{task_id}.yaml")
    command = task.expectations[0].command or []
    assert command[:3] == ["{python}", "-m", "micro_eval.tools.verify_protected"], command
    return command[command.index("--expected-sha256") + 1]


def _run_judge(fixture_copy: Path, digest: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "micro_eval.tools.verify_protected",
            "--protected-dir",
            "tests",
            "--expected-sha256",
            digest,
        ],
        cwd=fixture_copy,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_each_task_yaml_loads(task_id: str) -> None:
    task = load_task(TEMPLATE_DIR / "tasks" / f"{task_id}.yaml")
    assert task.id == task_id
    assert task.workspace.files == [f"fixtures/{task_id}"]
    assert task.expectations[0].type == "command"
    assert task.expectations[0].cwd == task_id


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_task_digest_matches_shipped_tests_directory(task_id: str) -> None:
    """The digest baked into the task YAML must match the shipped tests/, so a
    template edit that forgets to refresh the digest fails here, not at run time."""
    assert _expected_digest(task_id) == compute_protected_digest(TEMPLATE_DIR / "fixtures" / task_id / "tests")


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_no_judge_script_ships_inside_the_fixture(task_id: str) -> None:
    assert not (TEMPLATE_DIR / "fixtures" / task_id / "tools").exists()


def test_load_task_paths_resolves_all_five_tasks(tmp_path: Path) -> None:
    raw = yaml.safe_load((TEMPLATE_DIR / "eval.yaml").read_text())
    raw["configurations"] = [
        {
            "id": "dummy",
            "name": "dummy",
            "agent": {"name": "dummy", "command": ["cat"], "input_mode": "stdin", "output_mode": "stdout", "timeout_s": 10},
        }
    ]
    copy_dir = tmp_path / "starter-tasks-copy"
    shutil.copytree(TEMPLATE_DIR, copy_dir)
    config_path = copy_dir / "eval.yaml"
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False))

    config = load_config(config_path)
    tasks = load_task_paths(config_path, config)
    assert [task.id for task in tasks] == TASK_IDS


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_judge_buggy_fixed_and_tampered(tmp_path: Path, task_id: str) -> None:
    fixture_copy = tmp_path / task_id
    shutil.copytree(TEMPLATE_DIR / "fixtures" / task_id, fixture_copy)
    digest = _expected_digest(task_id)
    module_name = TASK_MODULES[task_id]

    # 1. Buggy code (as shipped) must fail on the tests themselves.
    buggy = _run_judge(fixture_copy, digest)
    assert buggy.returncode not in (0, 2), buggy.stdout + buggy.stderr

    # 2. Applying the known-good solution must pass.
    shutil.copy2(SOLUTIONS_DIR / task_id / module_name, fixture_copy / module_name)
    fixed = _run_judge(fixture_copy, digest)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr

    # 3. Editing the locked test file must fail even with the solution applied.
    test_file = next((fixture_copy / "tests").glob("test_*.py"))
    with test_file.open("a") as handle:
        handle.write("\n# tampered\n")
    tampered = _run_judge(fixture_copy, digest)
    assert tampered.returncode == 2, tampered.stdout + tampered.stderr
    assert "modified" in tampered.stderr


def test_judge_rejects_planted_package_init_in_tests_dir(tmp_path: Path) -> None:
    """Adding any file under tests/ (e.g. an __init__.py that monkeypatches
    unittest) changes the digest, so it is rejected before tests run."""
    task_id = TASK_IDS[0]
    fixture_copy = tmp_path / task_id
    shutil.copytree(TEMPLATE_DIR / "fixtures" / task_id, fixture_copy)
    shutil.copy2(SOLUTIONS_DIR / task_id / TASK_MODULES[task_id], fixture_copy / TASK_MODULES[task_id])
    (fixture_copy / "tests" / "__init__.py").write_text("import sys\nsys.exit(0)\n")

    result = _run_judge(fixture_copy, _expected_digest(task_id))
    assert result.returncode == 2


def test_judge_rejects_symlinked_tests_dir(tmp_path: Path) -> None:
    task_id = TASK_IDS[1]
    fixture_copy = tmp_path / task_id
    shutil.copytree(TEMPLATE_DIR / "fixtures" / task_id, fixture_copy)
    real_tests = tmp_path / "elsewhere-tests"
    shutil.move(str(fixture_copy / "tests"), str(real_tests))
    (fixture_copy / "tests").symlink_to(real_tests)

    result = _run_judge(fixture_copy, _expected_digest(task_id))
    assert result.returncode == 2


def test_judge_rejects_module_that_rewrites_tests_during_import(tmp_path: Path) -> None:
    """A fixed module that, on import, appends to a test file in the workspace
    must still be rejected: the tests run from a read-only snapshot and the
    workspace copy is re-digested after the run."""
    task_id = TASK_IDS[4]
    fixture_copy = tmp_path / task_id
    shutil.copytree(TEMPLATE_DIR / "fixtures" / task_id, fixture_copy)
    module_path = fixture_copy / TASK_MODULES[task_id]
    solution = (SOLUTIONS_DIR / task_id / TASK_MODULES[task_id]).read_text()
    test_name = next((fixture_copy / "tests").glob("test_*.py")).name
    hostile_suffix = (
        "\nimport pathlib as _p\n"
        f"_p.Path('tests/{test_name}').open('a').write('\\n# rewritten on import\\n')\n"
    )
    module_path.write_text(solution + hostile_suffix)

    result = _run_judge(fixture_copy, _expected_digest(task_id))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "modified while the tests ran" in result.stderr


def test_snapshot_rejects_symlink_and_cleanup_never_follows_links(tmp_path: Path) -> None:
    """A symlink inside the protected dir makes the snapshot digest fail (so the
    tests never run against it), and cleanup must not chmod through links."""
    from micro_eval.tools.verify_protected import _remove_snapshot, snapshot_protected_dir

    task_id = TASK_IDS[2]
    fixture_copy = tmp_path / task_id
    shutil.copytree(TEMPLATE_DIR / "fixtures" / task_id, fixture_copy)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep my mode\n")
    outside.chmod(0o644)
    (fixture_copy / "tests" / "planted").symlink_to(outside)

    with pytest.raises(ValueError):
        snapshot_protected_dir(fixture_copy / "tests", _expected_digest(task_id))
    assert outside.stat().st_mode & 0o777 == 0o644

    root = tmp_path / "fake-snapshot"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "link").symlink_to(outside)
    _remove_snapshot(root)
    assert not root.exists()
    assert outside.stat().st_mode & 0o777 == 0o644


def test_terminating_the_judge_kills_the_test_process(tmp_path: Path) -> None:
    """SIGTERM to verify_protected (what the validator sends on timeout) must
    take the unittest child down too, not leave it running."""
    import os
    import signal
    import time

    task_id = TASK_IDS[3]
    fixture_copy = tmp_path / task_id
    shutil.copytree(TEMPLATE_DIR / "fixtures" / task_id, fixture_copy)
    test_file = next((fixture_copy / "tests").glob("test_*.py"))
    test_file.write_text(
        "import os, pathlib, time, unittest\n"
        "class Slow(unittest.TestCase):\n"
        "    def test_sleep(self):\n"
        "        pathlib.Path(os.environ['PIDFILE']).write_text(str(os.getpid()))\n"
        "        time.sleep(60)\n"
    )
    digest = compute_protected_digest(fixture_copy / "tests")
    pid_file = tmp_path / "test.pid"
    judge = subprocess.Popen(
        [sys.executable, "-m", "micro_eval.tools.verify_protected", "--protected-dir", "tests", "--expected-sha256", digest],
        cwd=fixture_copy,
        env={**os.environ, "PIDFILE": str(pid_file)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if pid_file.exists():
                break
            time.sleep(0.1)
        assert pid_file.exists(), "unittest child never started"
        child_pid = int(pid_file.read_text())
        judge.send_signal(signal.SIGTERM)
        judge.wait(timeout=10)
        for _ in range(30):
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if judge.poll() is None:
            judge.kill()
