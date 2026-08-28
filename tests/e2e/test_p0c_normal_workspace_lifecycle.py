"""Integration coverage for the normal live-workspace finalization path."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from micro_eval.config.planner import build_run_plan
from micro_eval.engine.adapter import Redactor
from micro_eval.engine.cell_lifecycle import InvocationOutcome
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, Guardrails, OutputMode, ProjectConfigV2
from micro_eval.models.artifact import EvidenceItem
from micro_eval.models.evaluation import EvaluationResult
from micro_eval.models.run import AdapterResult, CellStatus, RunStatus
from micro_eval.models.task import TaskSpec, WorkspaceSpec, WorkspaceType


def _config(command: list[str], *, guardrails: Guardrails | None = None, **agent_kwargs):
    config = ProjectConfigV2(
        project_name="normal-lifecycle-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(name="agent", command=command, **agent_kwargs),
            )
        ],
        guardrails=guardrails or Guardrails(max_concurrency=1),
    )
    config.config_hash = "normal-lifecycle-config"
    return config


def _run(tmp_path: Path, task: TaskSpec, config: ProjectConfigV2, **kwargs):
    plan = build_run_plan(config, [task], project_root=tmp_path)
    return asyncio.run(ExecutionKernel(tmp_path, **kwargs).run(plan))


def test_blank_file_exists_is_validated_before_cleanup_and_committed(tmp_path: Path) -> None:
    task = TaskSpec(
        id="blank-live",
        name="Blank live workspace",
        input_payload="",
        expectations=[{"type": "file_exists", "value": "created.txt"}],
        workspace=WorkspaceSpec(type=WorkspaceType.blank),
    )
    config = _config(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('created.txt').write_text('created')",
        ]
    )
    callbacks: list[tuple[int, int, bool, bool]] = []

    def on_complete(done: int, total: int, result) -> None:
        run_dir = tmp_path / ".micro-eval" / "runs" / result.run_id
        callbacks.append((done, total, (run_dir / "cells" / result.cell_id / "result.json").exists(),
                          (run_dir / "cells" / result.cell_id / "evaluation.json").exists()))

    record = _run(tmp_path, task, config, on_cell_complete=on_complete)
    result = record.results[0]

    assert record.status == RunStatus.completed
    assert result.status.value == "pass"
    assert result.cell_snapshot is not None
    assert result.cell_snapshot.setup_exit_code is None
    assert result.cell_snapshot.cleanup_status == "cleaned"
    assert not Path(result.cell_snapshot.workspace_path).exists()
    assert record.evaluations
    assert result.evaluation_refs == [record.evaluations[0].evaluation_id]
    assert any(e.kind == "workspace_observation" for e in record.evidence)
    assert callbacks == [(1, 1, True, True)]


def test_files_command_expectation_reads_mutated_live_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "value.txt").write_text("before")
    task = TaskSpec(
        id="files-live",
        name="Files live workspace",
        input_payload="",
        expectations=[
            {
                "type": "command",
                "command": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; raise SystemExit(0 if Path('fixture/value.txt').read_text() == 'after' else 1)",
                ],
            }
        ],
        workspace=WorkspaceSpec(type=WorkspaceType.files, files=["fixture"]),
    )
    config = _config(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('fixture/value.txt').write_text('after')",
        ]
    )

    record = _run(tmp_path, task, config)
    result = record.results[0]

    assert result.status.value == "pass"
    assert result.cell_snapshot is not None
    assert result.cell_snapshot.cleanup_status == "cleaned"
    assert not Path(result.cell_snapshot.workspace_path).exists()


def _make_repo(path: Path) -> Path:
    path.mkdir()
    (path / "tracked.txt").write_text("before\n")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "tracked.txt"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "initial"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def test_git_diff_is_persisted_before_validator_side_effects_and_redacted(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "diff-secret-token")
    task = TaskSpec(
        id="git-diff-live",
        name="Git diff live workspace",
        input_payload="",
        expectations=[
            {
                "type": "command",
                "command": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('validator-sentinel.txt').write_text('validator')",
                ],
            }
        ],
        workspace=WorkspaceSpec(
            type=WorkspaceType.git_repo,
            path=str(repo),
            setup=[
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('setup.txt').write_text('setup')",
                ]
            ],
        ),
    )
    config = _config(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import os; "
                "Path('tracked.txt').write_text('after\\n'); "
                "Path('new.txt').write_text(os.environ['MICRO_EVAL_SECRET_TOKEN'])"
            ),
        ],
        required_secrets=["MICRO_EVAL_SECRET_TOKEN"],
    )

    record = _run(tmp_path, task, config)
    result = record.results[0]
    diff_ref = next(artifact for artifact in record.artifacts if artifact.kind == "diff")
    diff_path = tmp_path / ".micro-eval" / "runs" / record.id / diff_ref.path
    diff_text = diff_path.read_text()

    assert result.status.value == "pass"
    assert "tracked.txt" in diff_text
    assert "new.txt" in diff_text
    assert "setup.txt" in diff_text
    assert "validator-sentinel.txt" not in diff_text
    assert "diff-secret-token" not in diff_text
    assert "[REDACTED:MICRO_EVAL_SECRET_TOKEN]" in diff_text
    assert "diff_includes_setup_changes" in (diff_ref.warning or "")
    assert "diff_includes_setup_changes" in result.snapshot_gate_result.caveats
    assert result.cell_snapshot is not None
    assert result.cell_snapshot.setup_exit_code == 0
    assert result.cell_snapshot.cleanup_status == "cleaned"


def test_git_diff_skips_untracked_links_binary_and_over_cap_content(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    task = TaskSpec(
        id="git-diff-safety",
        name="Git diff safety",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
    )
    config = _config(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import os; "
                "Path('binary.bin').write_bytes(b'\\x00binary'); "
                "Path('large.txt').write_text('x' * 4096); "
                "Path('symlink.txt').symlink_to('tracked.txt'); "
                "os.link('tracked.txt', 'hardlink.txt')"
            ),
        ],
        guardrails=Guardrails(max_concurrency=1, artifact_cap_bytes=256),
    )

    record = _run(tmp_path, task, config)
    diff_ref = next(artifact for artifact in record.artifacts if artifact.kind == "diff")
    diff_path = tmp_path / ".micro-eval" / "runs" / record.id / diff_ref.path

    assert diff_path.read_text() == ""
    warning = diff_ref.warning or ""
    assert "untracked_binary_skipped" in warning
    assert "untracked_symlink_skipped" in warning
    assert "untracked_linked_file_skipped" in warning
    assert "untracked_file_exceeds_diff_cap" in warning


def test_git_diff_skips_deleted_tracked_symlink_from_head(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    (repo / "tracked-link.txt").symlink_to("tracked.txt")
    subprocess.run(["git", "add", "tracked-link.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "link"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    task = TaskSpec(
        id="git-deleted-link",
        name="Deleted tracked link",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
    )
    config = _config(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('tracked-link.txt').unlink()",
        ]
    )

    record = _run(tmp_path, task, config)
    diff_ref = next(artifact for artifact in record.artifacts if artifact.kind == "diff")
    diff_path = tmp_path / ".micro-eval" / "runs" / record.id / diff_ref.path

    assert "tracked-link.txt" not in diff_path.read_text()
    assert "tracked_symlink_skipped" in (diff_ref.warning or "")


def test_git_diff_fails_closed_when_tracked_mode_inventory_hits_cap(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    (repo / "tracked-link.txt").symlink_to("tracked.txt")
    subprocess.run(["git", "add", "tracked-link.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "link"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    task = TaskSpec(
        id="git-deleted-link-cap",
        name="Deleted tracked link with cap",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
    )
    config = _config(
        [sys.executable, "-c", "from pathlib import Path; Path('tracked-link.txt').unlink()"],
        guardrails=Guardrails(max_concurrency=1, artifact_cap_bytes=1),
    )

    record = _run(tmp_path, task, config)
    diff_ref = next(artifact for artifact in record.artifacts if artifact.kind == "diff")
    diff_path = tmp_path / ".micro-eval" / "runs" / record.id / diff_ref.path

    assert "tracked-link.txt" not in diff_path.read_text()
    warning = diff_ref.warning or ""
    assert "tracked_change_listing_truncated" in warning
    assert "tracked_diff_skipped" in warning


def test_git_diff_checks_head_blob_cap_before_persisting_replacement(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    (repo / "large.txt").write_text("old-secret-content\n" * 128)
    subprocess.run(["git", "add", "large.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "large"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    task = TaskSpec(
        id="git-head-cap",
        name="HEAD blob cap",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
    )
    config = _config(
        [sys.executable, "-c", "from pathlib import Path; Path('large.txt').write_text('small\\n')"],
        guardrails=Guardrails(max_concurrency=1, artifact_cap_bytes=256),
    )

    record = _run(tmp_path, task, config)
    diff_ref = next(artifact for artifact in record.artifacts if artifact.kind == "diff")
    diff_path = tmp_path / ".micro-eval" / "runs" / record.id / diff_ref.path

    diff_text = diff_path.read_text()
    assert "old-secret-content" not in diff_text
    assert "large.txt" not in diff_text
    assert "tracked_file_exceeds_diff_cap" in (diff_ref.warning or "")


def test_git_diff_keeps_source_head_baseline_when_agent_commits(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    task = TaskSpec(
        id="git-agent-commit",
        name="Agent commit baseline",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
    )
    config = _config(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import subprocess; "
                "Path('tracked.txt').write_text('after\\n'); "
                "subprocess.run(['git', 'add', 'tracked.txt'], check=True); "
                "subprocess.run(['git', '-c', 'user.email=agent@example.com', "
                "'-c', 'user.name=Agent', 'commit', '-m', 'agent'], check=True)"
            ),
        ]
    )

    record = _run(tmp_path, task, config)
    diff_ref = next(artifact for artifact in record.artifacts if artifact.kind == "diff")
    diff_path = tmp_path / ".micro-eval" / "runs" / record.id / diff_ref.path

    diff_text = diff_path.read_text()
    assert "tracked.txt" in diff_text
    assert "+after" in diff_text
    assert record.results[0].cell_snapshot is not None
    assert record.results[0].cell_snapshot.cleanup_status == "cleaned"


def test_directory_output_index_does_not_reindex_lifecycle_artifacts(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    task = TaskSpec(
        id="git-directory-output",
        name="Directory output lifecycle",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo)),
    )
    config = _config(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import os; "
                "Path('tracked.txt').write_text('changed\\n'); "
                "Path(os.environ['MICRO_EVAL_OUTPUT_DIR'], 'agent.txt').write_text('agent output')"
            ),
        ],
        output_mode=OutputMode.directory,
    )

    record = _run(tmp_path, task, config)
    file_artifacts = [artifact for artifact in record.artifacts if artifact.kind == "file"]

    assert any(artifact.path.endswith("agent.txt") for artifact in file_artifacts)
    assert not any(artifact.path.endswith("workspace.diff") for artifact in file_artifacts)
    assert any(artifact.kind == "diff" for artifact in record.artifacts)


def test_conversational_kernel_uses_the_same_cleanup_and_commit_tail(
    tmp_path: Path, monkeypatch
) -> None:
    task = TaskSpec(
        id="conversation-live",
        name="Conversation live workspace",
        input_payload="",
        scenario="A user asks a question",
        expected_outcome="The agent answers",
        expectations=[{"type": "contains", "value": "conversation-output", "stream": "stdout"}],
        workspace=WorkspaceSpec(type=WorkspaceType.blank),
    )
    config = _config([sys.executable, "-c", "print('unused')"])
    config.judge.enabled = True
    config.judge.provider = "deepeval_conversational"
    events: list[str] = []
    from micro_eval.engine import cell_lifecycle as lifecycle_module

    real_gate = lifecycle_module.evaluate_snapshot_gate

    def spy_gate(*args, **kwargs):
        events.append("snapshot_gate")
        return real_gate(*args, **kwargs)

    async def fake_invoke(self, cell, prepared):
        events.append("invoke")
        return InvocationOutcome(
            adapter_result=AdapterResult(
                status=CellStatus.passed,
                exit_code=0,
                stdout="conversation-output",
                output="conversation-output",
                trace_id=cell.cell_id,
            ),
            redactor=Redactor({}),
            conversation_test_case=object(),
            conversation_log=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "conversation-output"},
            ],
        )

    async def fake_score(**kwargs):
        evidence_id = f"{kwargs['evidence_prefix']}::conversational-judge"
        evaluation = EvaluationResult(
            evaluation_id=f"{kwargs['cell'].cell_id}::conversational-judge::test",
            cell_id=kwargs["cell"].cell_id,
            evaluator_type="conversational_judge",
            evaluator="test-conversational-judge",
            comment="conversation passed",
            pass_fail="pass",
            score=1.0,
            evidence_refs=[evidence_id],
        )
        evidence = EvidenceItem(
            evidence_id=evidence_id,
            kind="conversational_judge",
            summary="conversation passed",
            cell_id=kwargs["cell"].cell_id,
            status="passed",
            source_kind="evaluation_id",
            source_ref=evaluation.evaluation_id,
        )
        return evaluation, evidence

    monkeypatch.setattr("micro_eval.engine.cell_lifecycle.CellLifecycle._invoke_conversation", fake_invoke)
    monkeypatch.setattr("micro_eval.engine.cell_lifecycle.evaluate_snapshot_gate", spy_gate)
    monkeypatch.setattr("micro_eval.engine.cell_lifecycle.score_conversation", fake_score)

    record = _run(tmp_path, task, config)
    result = record.results[0]

    assert events[:2] == ["snapshot_gate", "invoke"]
    assert result.status == CellStatus.passed
    assert result.conversation_turns == 1
    assert result.conversation_ref is not None
    assert any(e.evaluator_type == "conversational_judge" for e in record.evaluations)
    assert result.cell_snapshot is not None
    assert result.cell_snapshot.cleanup_status == "cleaned"
    assert not Path(result.cell_snapshot.workspace_path).exists()
