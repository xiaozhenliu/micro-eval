"""Atomic run admission (round-7 review, 2026-09-13).

`enqueue_workspace_run` builds the plan, compares its replay digest with the
one the member previewed, and inserts the job — all under the workspace and
config locks. Every refusal is a JSON-serialisable `EnqueueRefused`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from micro_eval.cli.main import app
from micro_eval.config.planner import build_workspace_plan
from micro_eval.engine import git_refs as git_refs_module
from micro_eval.engine.git_refs import INVALID_GIT_REF_HINT
from micro_eval.models.run import RunPlan
from micro_eval.server import enqueue as enqueue_module
from micro_eval.server.enqueue import (
    EnqueueRefused,
    enqueue_workspace_run,
    plan_admission_digest,
    preview_workspace_run,
)
from micro_eval.server.queue import QueueDB, QueueFullError
from micro_eval.server.workspace import WorkspaceManager

CONFIG = (
    "project_name: x\n"
    "configurations:\n"
    "  - id: a\n"
    "    name: a\n"
    "    agent:\n"
    "      name: a\n"
    "      command: [cat]\n"
    "tasks:\n"
    "  - tasks/t.yaml\n"
)
TASK = 'id: t\nname: T\ninput_payload: "x"\n'


def _workspace(tmp_path: Path) -> tuple[WorkspaceManager, str, Path]:
    data_root = tmp_path / "data"
    data_root.mkdir()
    manager = WorkspaceManager(data_root)
    ws = manager.create(name="a", owner="alice")
    ws_dir = manager.workspaces_dir / ws.workspace_id
    (ws_dir / "eval.yaml").write_text(CONFIG)
    (ws_dir / "tasks").mkdir()
    (ws_dir / "tasks" / "t.yaml").write_text(TASK)
    return manager, ws.workspace_id, ws_dir


def _jobs(manager: WorkspaceManager) -> list[dict]:
    db = QueueDB(manager.data_root / "queue.db")
    try:
        return db.get_queue_dashboard()["queued"]
    finally:
        db.close()


def _make_source_repo(ws_dir: Path, name: str = "source") -> Path:
    """A committed git repo under the workspace used as a task workspace source."""
    source = ws_dir / name
    source.mkdir()
    (source / "README.md").write_text("ready\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "init"],
        cwd=source,
        check=True,
    )
    return source


def test_enqueue_builds_plan_and_reports_its_digest(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    preview = preview_workspace_run(manager, ws_id)
    expected = preview["plan_digest"]
    assert expected == plan_admission_digest(build_workspace_plan(ws_dir, strict_paths=True), ws_dir)
    assert preview["plan"]["cells"][0]["task"]["id"] == "t"

    result = enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=expected)

    assert result["plan_digest"] == expected
    jobs = _jobs(manager)
    assert [job["job_id"] for job in jobs] == [result["job_id"]]
    plan = RunPlan.model_validate_json(jobs[0]["plan_json"])
    assert plan_admission_digest(plan, ws_dir) == expected
    assert [cell.task.id for cell in plan.cells] == ["t"]


def test_enqueue_without_expected_digest_is_allowed(tmp_path: Path) -> None:
    manager, ws_id, _ = _workspace(tmp_path)
    result = enqueue_workspace_run(manager, ws_id, "alice")
    assert result["plan_digest"]
    assert len(_jobs(manager)) == 1


def test_enqueue_refuses_when_task_content_changed_since_preview(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    previewed = preview_workspace_run(manager, ws_id)["plan_digest"]
    # Only the task body changes; eval.yaml (and thus config_hash) is untouched.
    (ws_dir / "tasks" / "t.yaml").write_text('id: t\nname: T\ninput_payload: "y"\n')

    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=previewed)
    assert info.value.kind == "plan_changed"
    assert info.value.payload["plan_digest"] != previewed
    assert _jobs(manager) == []


def test_enqueue_refuses_archived_workspace(tmp_path: Path) -> None:
    manager, ws_id, _ = _workspace(tmp_path)
    manager.update(ws_id, status="archived")
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice")
    assert info.value.kind == "workspace_not_active"
    assert info.value.payload["status"] == "archived"
    assert _jobs(manager) == []


def test_enqueue_reports_plan_build_failure(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").unlink()
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice")
    assert info.value.kind == "plan_build_failed"
    assert "detail" in info.value.payload


def test_enqueue_reports_unknown_workspace(tmp_path: Path) -> None:
    manager, _, _ = _workspace(tmp_path)
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, "ws-20260913T000000Z-00000000", "alice")
    assert info.value.kind == "workspace_not_found"


def test_enqueue_reports_queue_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, ws_id, _ = _workspace(tmp_path)

    def full(self, **kwargs):  # noqa: ANN001 - test stub
        raise QueueFullError(100, 100)

    monkeypatch.setattr(QueueDB, "enqueue", full)
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice")
    assert info.value.kind == "queue_full"
    assert info.value.payload["maximum"] == 100


def test_workspace_enqueue_cli_prints_json_and_exit_codes(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    runner = CliRunner()
    root = str(manager.data_root)

    ok = runner.invoke(app, ["workspace", "enqueue", ws_id, "--owner", "alice", "--data-root", root])
    assert ok.exit_code == 0, ok.output
    payload = json.loads(ok.stdout)
    assert payload["job_id"].startswith("job-")
    assert payload["plan_digest"]

    stale = runner.invoke(
        app,
        [
            "workspace", "enqueue", ws_id,
            "--owner", "alice",
            "--expected-plan-digest", "not-the-digest",
            "--data-root", root,
        ],
    )
    assert stale.exit_code == 5
    assert json.loads(stale.output.strip().splitlines()[-1])["error"] == "plan_changed"
    assert len(_jobs(manager)) == 1


def test_admission_digest_changes_with_output_dir(tmp_path: Path) -> None:
    # config_hash / replay digest ignore output_dir; the admission digest must not.
    _, _, ws_dir = _workspace(tmp_path)
    before = plan_admission_digest(build_workspace_plan(ws_dir, strict_paths=True))
    (ws_dir / "eval.yaml").write_text(CONFIG + "output_dir: custom/runs\n")
    after = plan_admission_digest(build_workspace_plan(ws_dir, strict_paths=True))
    assert before != after


def test_admission_digest_is_stable_across_builds(tmp_path: Path) -> None:
    _, _, ws_dir = _workspace(tmp_path)
    first = plan_admission_digest(build_workspace_plan(ws_dir, strict_paths=True))
    second = plan_admission_digest(build_workspace_plan(ws_dir, strict_paths=True))
    assert first == second


def test_server_refuses_custom_output_dir(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "eval.yaml").write_text(CONFIG + "output_dir: custom/runs\n")
    for call in (lambda: preview_workspace_run(manager, ws_id), lambda: enqueue_workspace_run(manager, ws_id, "a")):
        with pytest.raises(EnqueueRefused) as info:
            call()
        assert info.value.kind == "plan_build_failed"
        assert "output_dir" in info.value.payload["detail"]
    assert _jobs(manager) == []


def test_enqueue_honours_server_json_max_queue_size(tmp_path: Path) -> None:
    manager, ws_id, _ = _workspace(tmp_path)
    (manager.data_root / "server.json").write_text(json.dumps({"max_queue_size": 1}))
    enqueue_workspace_run(manager, ws_id, "alice")
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice")
    assert info.value.kind == "queue_full"
    assert info.value.payload["maximum"] == 1


def test_enqueue_refuses_task_reached_through_symlinked_directory(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    outside = tmp_path_factory.mktemp("outside")
    (outside / "t.yaml").write_text(TASK)
    import shutil

    shutil.rmtree(ws_dir / "tasks")
    (ws_dir / "tasks").symlink_to(outside)
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    assert info.value.kind == "plan_build_failed"
    assert "symlink" in info.value.payload["detail"]


def test_workspace_enqueue_cli_dry_run(tmp_path: Path) -> None:
    manager, ws_id, _ = _workspace(tmp_path)
    result = CliRunner().invoke(app, ["workspace", "enqueue", ws_id, "--dry-run", "--data-root", str(manager.data_root)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert len(payload["plan_digest"]) == 64
    assert payload["plan"]["output_dir"] == ".micro-eval/runs"
    assert _jobs(manager) == []


def test_plan_build_failure_detail_omits_input_values_and_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pasted secret inside a broken task must not come back in the refusal.
    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "sk-live-9f8e7d")
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(
        'id: t\nname: T\ninput_payload: "x"\nbusiness_impact_tier: sk-live-9f8e7d\n'
    )
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    detail = info.value.payload["detail"]
    assert info.value.kind == "plan_build_failed"
    assert "sk-live-9f8e7d" not in detail
    assert "input_value=<omitted>" in detail or "input_value" not in detail
    assert "For further information" not in detail


def test_loader_refuses_tasks_that_is_not_a_list(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "eval.yaml").write_text(CONFIG.replace("tasks:\n  - tasks/t.yaml\n", "tasks: tasks/t.yaml\n"))
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    assert "tasks must be a list" in info.value.payload["detail"]


def test_plan_build_failure_detail_has_no_absolute_paths(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "eval.yaml").write_text("project_name: [unclosed\n")
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    detail = info.value.payload["detail"]
    assert str(ws_dir) not in detail
    assert "/" not in detail.replace("<path>", "")


def test_loader_refuses_explicit_null_tasks(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "eval.yaml").write_text(CONFIG.replace("tasks:\n  - tasks/t.yaml\n", "tasks: null\n"))
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    assert "tasks must be a list" in info.value.payload["detail"]


def test_safe_detail_masks_workspace_paths_with_spaces(tmp_path: Path) -> None:
    from micro_eval.server.enqueue import _safe_detail

    root = tmp_path / "My Project" / "workspaces" / "ws-x"
    message = f"Invalid YAML in {root}/eval.yaml: boom"
    cleaned = _safe_detail(message, (root, tmp_path))
    assert "My Project" not in cleaned
    assert cleaned.startswith("Invalid YAML in <path>")


def test_enqueue_refuses_a_plan_that_embeds_a_declared_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Round-13 review: queue.db stores the plan verbatim, so a declared secret
    # value pasted into a command/prompt must never reach it.
    monkeypatch.setenv("MICRO_EVAL_SECRET_API", "sk-queue-leak")
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text('id: t\nname: T\ninput_payload: "use sk-queue-leak"\n')
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice")
    assert info.value.kind == "plan_build_failed"
    assert "MICRO_EVAL_SECRET_API" in info.value.payload["detail"]
    assert "sk-queue-leak" not in info.value.payload["detail"]
    assert _jobs(manager) == []
    assert not (manager.data_root / "queue.db").exists() or "sk-queue-leak" not in (manager.data_root / "queue.db").read_bytes().decode("latin-1")


def test_strict_loader_reserves_runtime_directory_for_tasks(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / ".micro-eval").mkdir(exist_ok=True)
    (ws_dir / ".micro-eval" / "t.yaml").write_text(TASK)
    (ws_dir / "eval.yaml").write_text(CONFIG.replace("tasks/t.yaml", ".micro-eval/t.yaml"))
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    assert "runtime directory" in info.value.payload["detail"]


def test_enqueue_secret_scan_is_not_fooled_by_json_escaping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A secret containing a double quote serialises as a\"b in JSON; scanning
    # the serialised text would miss it (round-14 review).
    monkeypatch.setenv("MICRO_EVAL_SECRET_API", 'a"b')
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text('id: t\nname: T\ninput_payload: "token a\\"b here"\n')
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice")
    assert info.value.kind == "plan_build_failed"
    assert _jobs(manager) == []


FILES_TASK = 'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  type: files\n  files: [src]\n'


def test_admission_digest_covers_workspace_source_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The compatibility hash below includes the tool version recorded with the
    # original fixture. Keep that input stable across release version bumps.
    monkeypatch.setattr("micro_eval.config.planner.__version__", "0.4.6")
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(FILES_TASK)
    (ws_dir / "src").mkdir()
    (ws_dir / "src" / "a.py").write_text("print(1)\n")
    previewed = preview_workspace_run(manager, ws_id)["plan_digest"]
    # Baseline captured before GRO-576: source validation must not change a
    # valid plan's admission digest.
    assert previewed == "a84a6795cccf20fe766985fd6d25f5395470ed891c9439e8a9dd890a5fe16098"
    assert previewed == preview_workspace_run(manager, ws_id)["plan_digest"]

    (ws_dir / "src" / "a.py").write_text("print(2)\n")
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=previewed)
    assert info.value.kind == "plan_changed"

    fresh = preview_workspace_run(manager, ws_id)["plan_digest"]
    enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=fresh)
    assert len(_jobs(manager)) == 1


@pytest.mark.parametrize(
    ("workspace", "directory", "detail"),
    [
        ("type: files\n  files: [missing]", None, "task t: workspace source not found: missing"),
        ("type: files\n  files: [src/missing]", "src", "task t: workspace source not found: src/missing"),
        ("type: git_repo", None, "task t: workspace source not found: ."),
        ("type: git_repo\n  path: missing", None, "task t: workspace source not found: missing"),
        ("type: git_repo\n  path: source", "source", "task t: workspace source is not a git repo: source"),
    ],
)
def test_source_preflight_refuses_preview_and_enqueue(
    tmp_path: Path, workspace: str, directory: str | None, detail: str
) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(f'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  {workspace}\n')
    if directory:
        (ws_dir / directory).mkdir()
    for call in (lambda: preview_workspace_run(manager, ws_id), lambda: enqueue_workspace_run(manager, ws_id, "alice")):
        with pytest.raises(EnqueueRefused) as info:
            call()
        assert info.value.kind == "plan_build_failed"
        assert info.value.payload["detail"] == detail
        assert str(ws_dir) not in info.value.payload["detail"]
    assert _jobs(manager) == []


def test_source_preflight_refuses_unresolvable_git_ref(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(
        'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  type: git_repo\n  path: source\n  ref: missing-ref\n'
    )
    source = ws_dir / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "README.md").write_text("ready\n")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "init"],
        cwd=source,
        check=True,
    )
    for call in (lambda: preview_workspace_run(manager, ws_id), lambda: enqueue_workspace_run(manager, ws_id, "alice")):
        with pytest.raises(EnqueueRefused) as info:
            call()
        assert info.value.kind == "plan_build_failed"
        # The plan-build stage now resolves the ref strictly and refuses
        # before the fd preflight runs (GRO-972).
        assert info.value.payload["detail"] == "[task=t] git ref cannot be resolved to a commit"
        assert info.value.payload["reason"] == "invalid_git_ref"
        assert info.value.payload["hint"] == INVALID_GIT_REF_HINT
        assert str(ws_dir) not in info.value.payload["detail"]
    assert _jobs(manager) == []

    (ws_dir / "tasks" / "t.yaml").write_text(
        'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  type: git_repo\n  path: source\n  ref: HEAD\n'
    )
    preview = preview_workspace_run(manager, ws_id)
    enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=preview["plan_digest"])
    assert len(_jobs(manager)) == 1


@pytest.mark.parametrize(
    "ref",
    ["--help", "--show-toplevel", "HEAD^{tree}", "HEAD:README.md", " ", "missing-ref"],
)
def test_git_preflight_refuses_option_and_non_commit_refs(tmp_path: Path, ref: str) -> None:
    """GRO-972: option-like and non-commit refs are refused with reason+hint."""
    _, _, ws_dir = _workspace(tmp_path)
    _make_source_repo(ws_dir)
    with pytest.raises(EnqueueRefused) as info:
        enqueue_module._preflight_git_source(ws_dir, "t", "source", ref)
    assert info.value.kind == "plan_build_failed"
    assert info.value.payload["detail"] == "task t: git ref cannot be resolved for workspace source: source"
    assert info.value.payload["reason"] == "invalid_git_ref"
    assert info.value.payload["hint"] == INVALID_GIT_REF_HINT


def test_git_preflight_reports_missing_git_as_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing git executable is a fixed tool error, not a missing-branch verdict."""
    _, _, ws_dir = _workspace(tmp_path)
    _make_source_repo(ws_dir)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(EnqueueRefused) as info:
        enqueue_module._preflight_git_source(ws_dir, "t", "source", "main")
    assert info.value.kind == "plan_build_failed"
    assert info.value.payload["detail"] == "task t: git executable unavailable for workspace source: source"
    assert "reason" not in info.value.payload
    assert "hint" not in info.value.payload


def test_plan_build_ref_refusal_carries_reason_and_hint(tmp_path: Path) -> None:
    """The plan-build stage maps the ConfigError reason to reason+hint too."""
    manager, ws_id, ws_dir = _workspace(tmp_path)
    _make_source_repo(ws_dir)
    (ws_dir / "tasks" / "t.yaml").write_text(
        'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  type: git_repo\n  path: source\n  ref: "--help"\n'
    )
    for call in (lambda: preview_workspace_run(manager, ws_id), lambda: enqueue_workspace_run(manager, ws_id, "alice")):
        with pytest.raises(EnqueueRefused) as info:
            call()
        assert info.value.kind == "plan_build_failed"
        assert info.value.payload["reason"] == "invalid_git_ref"
        assert info.value.payload["hint"] == INVALID_GIT_REF_HINT
        assert "[task=t]" in info.value.payload["detail"]
        assert str(ws_dir) not in info.value.payload["detail"]
    assert _jobs(manager) == []

    (ws_dir / "tasks" / "t.yaml").write_text(
        'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  type: git_repo\n  path: source\n  ref: main\n'
    )
    preview = preview_workspace_run(manager, ws_id)
    enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=preview["plan_digest"])
    assert len(_jobs(manager)) == 1


def test_moving_annotated_tag_after_preview_returns_plan_changed(tmp_path: Path) -> None:
    """Round-1 coverage: a stale preview digest (tag moved to another commit)
    is refused with plan_changed; refreshing the preview admits the run."""
    manager, ws_id, ws_dir = _workspace(tmp_path)
    source = _make_source_repo(ws_dir)

    def _write_task(ref: str) -> None:
        (ws_dir / "tasks" / "t.yaml").write_text(
            'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  type: git_repo\n  path: source\n'
            f'  ref: "{ref}"\n'
        )

    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "commit", "--allow-empty", "-qm", "second"],
        check=True,
    )
    first = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD~1"], check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "tag", "-a", "ann", "-m", "m", first],
        check=True,
    )
    _write_task("ann")
    stale = preview_workspace_run(manager, ws_id)["plan_digest"]

    subprocess.run(["git", "-C", str(source), "tag", "-a", "-f", "ann", "-m", "m", "HEAD"], check=True)
    with pytest.raises(EnqueueRefused) as info:
        enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=stale)
    assert info.value.kind == "plan_changed"
    assert _jobs(manager) == []

    fresh = preview_workspace_run(manager, ws_id)["plan_digest"]
    assert fresh != stale
    enqueue_workspace_run(manager, ws_id, "alice", expected_plan_digest=fresh)
    assert len(_jobs(manager)) == 1


@pytest.mark.parametrize("dry_run", [True, False])
def test_workspace_enqueue_cli_refuses_invalid_git_ref(
    tmp_path: Path, dry_run: bool
) -> None:
    """The CLI refusal payload keeps the exit code 4 and surfaces reason+hint."""
    manager, ws_id, ws_dir = _workspace(tmp_path)
    _make_source_repo(ws_dir)
    (ws_dir / "tasks" / "t.yaml").write_text(
        'id: t\nname: T\ninput_payload: "x"\nworkspace:\n  type: git_repo\n  path: source\n  ref: missing-ref\n'
    )
    args = ["workspace", "enqueue", ws_id, "--data-root", str(manager.data_root)]
    args.append("--dry-run" if dry_run else "--owner")
    if not dry_run:
        args.append("alice")

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 4
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["error"] == "plan_build_failed"
    assert payload["detail"] == "[task=t] git ref cannot be resolved to a commit"
    assert payload["reason"] == "invalid_git_ref"
    assert payload["hint"] == INVALID_GIT_REF_HINT
    assert str(ws_dir) not in result.output
    assert _jobs(manager) == []


@pytest.mark.parametrize("dry_run", [True, False])
def test_workspace_enqueue_cli_refuses_missing_source_before_queue(tmp_path: Path, dry_run: bool) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(FILES_TASK.replace("[src]", "[src/missing]"))
    (ws_dir / "src").mkdir()
    args = ["workspace", "enqueue", ws_id, "--data-root", str(manager.data_root)]
    if dry_run:
        args.append("--dry-run")
    else:
        args.extend(["--owner", "alice"])

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 4
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload == {"error": "plan_build_failed", "detail": "task t: workspace source not found: src/missing"}
    assert str(ws_dir) not in result.output
    assert _jobs(manager) == []


@pytest.mark.parametrize("swap_parent", [False, True])
@pytest.mark.parametrize("ref, accepted", [("source-only", True), ("outside-only", False)])
def test_git_preflight_uses_open_fd_after_source_path_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, swap_parent: bool, ref: str, accepted: bool
) -> None:
    _, _, ws_dir = _workspace(tmp_path)
    if swap_parent:
        source_parent = ws_dir / "parent"
        source = source_parent / "source"
        outside_parent = tmp_path / "outside-parent"
        outside = outside_parent / "source"
        raw = "parent/source"
    else:
        source_parent = ws_dir
        source = ws_dir / "source"
        outside_parent = tmp_path
        outside = tmp_path / "outside"
        raw = "source"

    for repo in (source, outside):
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",
             "commit", "--allow-empty", "-qm", "init"],
            check=True,
        )
    subprocess.run(["git", "-C", str(source), "tag", "source-only"], check=True)
    subprocess.run(["git", "-C", str(outside), "tag", "outside-only"], check=True)

    real_run = subprocess.run
    swapped = False

    def swap_before_git(argv, **kwargs):  # noqa: ANN001 - subprocess test wrapper
        nonlocal swapped
        if argv[:2] == ["git", "rev-parse"] and not swapped:
            swapped = True
            if swap_parent:
                source_parent.rename(ws_dir / "parent-original")
                source_parent.symlink_to(outside_parent, target_is_directory=True)
            else:
                source.rename(ws_dir / "source-original")
                source.symlink_to(outside, target_is_directory=True)
        return real_run(argv, **kwargs)

    # The strict resolver lives in engine.git_refs; patching its subprocess
    # attribute replaces git globally for this test, so the swap still races
    # the very rev-parse that resolves the ref (GRO-576 -> GRO-972).
    monkeypatch.setattr(git_refs_module.subprocess, "run", swap_before_git)
    if accepted:
        enqueue_module._preflight_git_source(ws_dir, "t", raw, ref)
    else:
        with pytest.raises(EnqueueRefused) as info:
            enqueue_module._preflight_git_source(ws_dir, "t", raw, ref)
        assert info.value.kind == "plan_build_failed"
        assert info.value.payload["detail"] == f"task t: git ref cannot be resolved for workspace source: {raw}"

    assert swapped


def test_admission_digest_refuses_symlinked_source(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(FILES_TASK)
    outside = tmp_path_factory.mktemp("outside")
    (outside / "a.py").write_text("x")
    (ws_dir / "src").symlink_to(outside)
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    assert "symlink" in info.value.payload["detail"]


def test_admission_digest_refuses_source_outside_workspace(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(FILES_TASK.replace("[src]", '["../src"]'))
    with pytest.raises(EnqueueRefused) as info:
        preview_workspace_run(manager, ws_id)
    assert "relative" in info.value.payload["detail"]


def _run_with_timeout(fn, seconds: float):
    import threading

    box: dict = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - propagate to the caller
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "call blocked"
    if "error" in box:
        raise box["error"]
    return box.get("value")


def test_fifo_in_workspace_source_is_refused_without_blocking(tmp_path: Path) -> None:
    # Round-17 review: a FIFO opened O_RDONLY blocks until a writer appears.
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").write_text(FILES_TASK)
    (ws_dir / "src").mkdir()
    os.mkfifo(ws_dir / "src" / "pipe")
    with pytest.raises(EnqueueRefused) as info:
        _run_with_timeout(lambda: preview_workspace_run(manager, ws_id), 5.0)
    assert "unsupported" in info.value.payload["detail"]


def test_fifo_as_task_file_is_refused_without_blocking(tmp_path: Path) -> None:
    manager, ws_id, ws_dir = _workspace(tmp_path)
    (ws_dir / "tasks" / "t.yaml").unlink()
    os.mkfifo(ws_dir / "tasks" / "t.yaml")
    with pytest.raises(EnqueueRefused) as info:
        _run_with_timeout(lambda: preview_workspace_run(manager, ws_id), 5.0)
    assert info.value.kind == "plan_build_failed"
