"""P0-b acceptance coverage for workspaces, snapshots, and redaction."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from micro_eval.config.planner import build_run_plan
from micro_eval.engine.kernel import ExecutionKernel
from micro_eval.models.configuration import AgentSpec, ConfigurationSpec, Guardrails, OutputMode, InputMode, ProjectConfigV2
from micro_eval.models.task import TaskSpec, WorkspaceSpec, WorkspaceType


def test_git_repo_workspace_runs_in_isolated_worktree_with_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "sample-repo"
    repo.mkdir()
    (repo / "marker.txt").write_text("from-worktree")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "marker.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "Initial"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    task = TaskSpec(
        id="git-task",
        name="Git task",
        input_payload="",
        expectations=[{"type": "contains", "value": "from-worktree", "stream": "stdout"}],
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo), ref="HEAD"),
    )
    config = ProjectConfigV2(
        project_name="workspace-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[
                        sys.executable,
                        "-c",
                        "import pathlib; print(pathlib.Path.cwd()); print(pathlib.Path('marker.txt').read_text())",
                    ],
                ),
            )
        ],
        guardrails=Guardrails(max_concurrency=1),
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    result = record.results[0]
    assert "from-worktree" in result.stdout_summary
    assert result.cell_snapshot is not None
    assert result.snapshot_gate_result is not None
    assert result.snapshot_gate_result.status == "pass"
    assert result.cell_snapshot.git_commit == record.same_start_snapshot.git_commit
    workspace_path = Path(result.cell_snapshot.workspace_path)
    assert workspace_path != tmp_path
    assert workspace_path.is_relative_to(tmp_path / ".micro-eval" / "workspaces" / plan.run_id)
    assert not workspace_path.exists()
    assert result.cell_snapshot.cleanup_status == "cleaned"


def test_files_workspace_stays_under_project_workspaces_dir(tmp_path: Path) -> None:
    fixture = tmp_path / "workspace"
    fixture.mkdir()
    (fixture / "marker.txt").write_text("from-copied-files")
    task = TaskSpec(
        id="files-task",
        name="Files task",
        input_payload="",
        expectations=[{"type": "contains", "value": "from-copied-files", "stream": "stdout"}],
        workspace=WorkspaceSpec(type=WorkspaceType.files, files=["workspace"]),
    )
    config = ProjectConfigV2(
        project_name="files-workspace-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[
                        sys.executable,
                        "-c",
                        (
                            "import pathlib; "
                            "print(pathlib.Path.cwd()); "
                            "print(pathlib.Path('workspace/marker.txt').read_text())"
                        ),
                    ],
                ),
            )
        ],
        guardrails=Guardrails(max_concurrency=1),
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    result = record.results[0]
    assert "from-copied-files" in result.stdout_summary
    assert result.cell_snapshot is not None
    workspace_path = Path(result.cell_snapshot.workspace_path)
    assert workspace_path.is_relative_to(tmp_path / ".micro-eval" / "workspaces" / plan.run_id)
    assert not workspace_path.exists()
    assert result.cell_snapshot.cleanup_status == "cleaned"


def test_replay_digest_changes_when_git_workspace_commit_changes(tmp_path: Path) -> None:
    repo = tmp_path / "sample-repo"
    repo.mkdir()
    (repo / "marker.txt").write_text("one")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "marker.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "One"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    task = TaskSpec(
        id="git-task",
        name="Git task",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo), ref="HEAD"),
    )
    config = ProjectConfigV2(
        project_name="workspace-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(name="agent", command=[sys.executable, "-c", "print('ok')"]),
            )
        ],
        guardrails=Guardrails(max_concurrency=1),
    )
    config.config_hash = "config-hash"
    first = build_run_plan(config, [task], project_root=tmp_path)

    (repo / "marker.txt").write_text("two")
    subprocess.run(["git", "add", "marker.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "Two"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    second = build_run_plan(config, [task], project_root=tmp_path)

    assert first.replay_canonical is not None
    assert second.replay_canonical is not None
    assert first.replay_canonical.workspace_fingerprint != second.replay_canonical.workspace_fingerprint
    assert first.replay_canonical.digest != second.replay_canonical.digest


def test_python_placeholder_uses_current_interpreter(tmp_path: Path) -> None:
    task = TaskSpec(
        id="python-placeholder",
        name="Python placeholder",
        input_payload="",
        expectations=[{"type": "contains", "value": sys.executable, "stream": "stdout"}],
    )
    config = ProjectConfigV2(
        project_name="python-placeholder-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=["{python}", "-c", "import sys; print(sys.executable)"],
                ),
            )
        ],
        guardrails=Guardrails(max_concurrency=1),
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    result = record.results[0]
    assert result.status.value == "pass"
    assert sys.executable in result.stdout_summary


def test_snapshot_gate_uses_task_workspace_map_for_moved_ref(tmp_path: Path) -> None:
    repo = tmp_path / "sample-repo"
    repo.mkdir()
    (repo / "marker.txt").write_text("one")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "marker.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "One"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    task = TaskSpec(
        id="git-task",
        name="Git task",
        input_payload="",
        workspace=WorkspaceSpec(type=WorkspaceType.git_repo, path=str(repo), ref="HEAD"),
    )
    config = ProjectConfigV2(
        project_name="workspace-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(name="agent", command=[sys.executable, "-c", "print('ok')"]),
            )
        ],
        guardrails=Guardrails(max_concurrency=1),
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    (repo / "marker.txt").write_text("two")
    subprocess.run(["git", "add", "marker.txt"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "Two"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    result = record.results[0]

    assert result.snapshot_gate_result is not None
    assert result.snapshot_gate_result.status == "warn"
    assert "workspace_map" in result.snapshot_gate_result.mismatch_fields
    assert record.decision is not None
    assert record.decision.verdict.value == "not_comparable"


def test_output_file_missing_does_not_index_input_as_output(tmp_path: Path) -> None:
    task = TaskSpec(id="file-task", name="File task", input_payload="secret input")
    config = ProjectConfigV2(
        project_name="file-output-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[sys.executable, "-c", "print('did not write output file')"],
                    input_mode=InputMode.file,
                    output_mode=OutputMode.file,
                ),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))

    result = record.results[0]
    assert result.status.value == "error"
    assert result.failure_mode == "output_file_missing"
    assert all(not artifact.path.endswith("input.txt") for artifact in record.artifacts)
    assert all(artifact.kind != "output" for artifact in record.artifacts)


def test_declared_secret_is_redacted_before_artifacts_and_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_TOKEN", "super-secret-token")
    task = TaskSpec(id="secret-task", name="Secret task", input_payload="")
    config = ProjectConfigV2(
        project_name="secret-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[sys.executable, "-c", "import os; print(os.environ['MICRO_EVAL_SECRET_TOKEN'])"],
                    required_secrets=["MICRO_EVAL_SECRET_TOKEN"],
                ),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    run_dir = tmp_path / ".micro-eval" / "runs" / record.id
    persisted_text = "\n".join(path.read_text(errors="ignore") for path in run_dir.rglob("*.txt"))
    evidence_text = "\n".join(item.summary for item in record.evidence)

    assert "super-secret-token" not in persisted_text
    assert "super-secret-token" not in evidence_text
    assert "[REDACTED:MICRO_EVAL_SECRET_TOKEN]" in persisted_text


def test_undeclared_micro_eval_secret_in_task_input_is_redacted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_UNDECLARED", "undeclared-secret")
    task = TaskSpec(id="secret-task", name="Secret task", input_payload="undeclared-secret")
    config = ProjectConfigV2(
        project_name="secret-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(name="agent", command=[sys.executable, "-c", "import sys; print(sys.stdin.read())"]),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    run_dir = tmp_path / ".micro-eval" / "runs" / record.id
    persisted_text = "\n".join(path.read_text(errors="ignore") for path in run_dir.rglob("*.txt"))

    assert "undeclared-secret" not in persisted_text
    assert "[REDACTED:MICRO_EVAL_SECRET_UNDECLARED]" in persisted_text


def test_short_micro_eval_secret_value_is_redacted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_SHORT", "xy")
    task = TaskSpec(id="short-secret-task", name="Short secret task", input_payload="xy")
    config = ProjectConfigV2(
        project_name="short-secret-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(name="agent", command=[sys.executable, "-c", "import sys; print(sys.stdin.read())"]),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    run_dir = tmp_path / ".micro-eval" / "runs" / record.id
    persisted_text = "\n".join(path.read_text(errors="ignore") for path in run_dir.rglob("*.txt"))

    assert "xy" not in persisted_text
    assert "[REDACTED:MICRO_EVAL_SECRET_SHORT]" in persisted_text


def test_binary_directory_artifact_records_redaction_warning(tmp_path: Path) -> None:
    task = TaskSpec(id="binary-task", name="Binary task", input_payload="")
    config = ProjectConfigV2(
        project_name="binary-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[
                        sys.executable,
                        "-c",
                        "from pathlib import Path; import os; Path(os.environ['MICRO_EVAL_OUTPUT_DIR'], 'blob.bin').write_bytes(b'abc\\x00secret')",
                    ],
                    output_mode=OutputMode.directory,
                ),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    binary = next(artifact for artifact in record.artifacts if artifact.path.endswith("blob.bin"))

    assert binary.media_type == "application/octet-stream"
    assert binary.redacted is False
    assert binary.warning == "binary_redaction_skipped"


def test_directory_artifact_symlink_is_skipped(tmp_path: Path) -> None:
    host_file = tmp_path / "host-secret.txt"
    host_file.write_text("host-secret")
    task = TaskSpec(id="symlink-task", name="Symlink task", input_payload="")
    config = ProjectConfigV2(
        project_name="symlink-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; import os; "
                            f"Path(os.environ['MICRO_EVAL_OUTPUT_DIR'], 'leak.txt').symlink_to({str(host_file)!r})"
                        ),
                    ],
                    output_mode=OutputMode.directory,
                ),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    persisted_text = "\n".join(
        path.read_text(errors="ignore") for path in (tmp_path / ".micro-eval" / "runs" / record.id).rglob("*.txt")
    )

    assert all(not artifact.path.endswith("leak.txt") for artifact in record.artifacts)
    assert "host-secret" not in persisted_text
    assert "symlink artifact skipped" in record.results[0].output_summary


def test_reserved_stdout_symlink_is_replaced_without_host_write(tmp_path: Path) -> None:
    host_file = tmp_path / "host-target.txt"
    host_file.write_text("host-original")
    task = TaskSpec(id="reserved-task", name="Reserved task", input_payload="")
    config = ProjectConfigV2(
        project_name="reserved-symlink-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; import os; "
                            f"Path(os.environ['MICRO_EVAL_OUTPUT_DIR'], 'stdout.txt').symlink_to({str(host_file)!r}); "
                            "print('agent stdout')"
                        ),
                    ],
                ),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    stdout_artifact = next(artifact for artifact in record.artifacts if artifact.kind == "stdout")
    stdout_path = tmp_path / ".micro-eval" / "runs" / record.id / stdout_artifact.path

    assert host_file.read_text() == "host-original"
    assert not stdout_path.is_symlink()
    assert stdout_path.read_text() == "agent stdout\n"


def test_output_mode_file_symlink_and_hardlink_are_skipped(tmp_path: Path) -> None:
    for link_kind in ["symlink", "hardlink"]:
        project_root = tmp_path / link_kind
        project_root.mkdir()
        host_file = project_root / "host-target.txt"
        host_file.write_text("host-original")
        if link_kind == "symlink":
            command = (
                "from pathlib import Path; import os; "
                f"target={str(host_file)!r}; output=os.environ['MICRO_EVAL_OUTPUT_FILE']; "
                "Path(output).symlink_to(target)"
            )
        else:
            command = (
                "import os; "
                f"target={str(host_file)!r}; output=os.environ['MICRO_EVAL_OUTPUT_FILE']; "
                "os.link(target, output)"
            )
        task = TaskSpec(id=f"{link_kind}-task", name="File link task", input_payload="")
        config = ProjectConfigV2(
            project_name=f"{link_kind}-test",
            configurations=[
                ConfigurationSpec(
                    id="agent",
                    name="agent",
                    agent=AgentSpec(
                        name="agent",
                        command=[sys.executable, "-c", command],
                        output_mode=OutputMode.file,
                    ),
                )
            ],
        )
        config.config_hash = "config-hash"
        plan = build_run_plan(config, [task], project_root=project_root)

        record = asyncio.run(ExecutionKernel(project_root).run(plan))
        result = record.results[0]

        assert host_file.read_text() == "host-original"
        assert result.status.value == "error"
        assert result.failure_mode == "output_file_missing"
        output_artifact = next(artifact for artifact in record.artifacts if artifact.path.endswith("output.txt"))
        output_path = project_root / ".micro-eval" / "runs" / record.id / output_artifact.path
        assert not output_path.is_symlink()
        assert "linked output file skipped" in output_path.read_text()
        assert "host-original" not in output_path.read_text()


def test_oversized_directory_artifact_is_marked_skipped_without_text_exposure(tmp_path: Path) -> None:
    task = TaskSpec(id="large-task", name="Large task", input_payload="")
    config = ProjectConfigV2(
        project_name="large-artifact-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; import os; "
                            "Path(os.environ['MICRO_EVAL_OUTPUT_DIR'], 'large.txt').write_text('x' * 128)"
                        ),
                    ],
                    output_mode=OutputMode.directory,
                ),
            )
        ],
        guardrails=Guardrails(artifact_cap_bytes=16),
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    large = next(artifact for artifact in record.artifacts if artifact.path.endswith("large.txt"))

    assert large.warning == "skipped_oversized"
    assert large.sha256 == ""
    assert large.redacted is False


def test_workspace_setup_does_not_inherit_micro_eval_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_HOST", "setup-secret")
    task = TaskSpec(
        id="setup-task",
        name="Setup task",
        input_payload="",
        workspace=WorkspaceSpec(
            type=WorkspaceType.blank,
            setup=[
                [
                    sys.executable,
                    "-c",
                    "import os, pathlib; pathlib.Path('leak.txt').write_text(os.environ.get('MICRO_EVAL_SECRET_HOST', 'missing'))",
                ]
            ],
        ),
        expectations=[{"type": "contains", "value": "missing", "stream": "stdout"}],
    )
    config = ProjectConfigV2(
        project_name="setup-env-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[sys.executable, "-c", "from pathlib import Path; print(Path('leak.txt').read_text())"],
                ),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    result = record.results[0]

    assert result.status.value == "pass"
    assert "setup-secret" not in result.stdout_summary


def test_repetitions_write_decision_json_with_pass_at_k(tmp_path: Path) -> None:
    task = TaskSpec(
        id="repeat-task",
        name="Repeat task",
        input_payload="",
        expectations=[{"type": "contains", "value": "ok", "stream": "stdout"}],
    )
    config = ProjectConfigV2(
        project_name="repeat-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                repetitions=3,
                agent=AgentSpec(name="agent", command=[sys.executable, "-c", "print('ok')"]),
            )
        ],
        guardrails=Guardrails(max_concurrency=1),
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    decision_path = tmp_path / ".micro-eval" / "runs" / record.id / "decision.json"

    assert decision_path.exists()
    assert record.decision is not None
    assert record.decision.decision_report_id.startswith(f"{record.id}::decision::")
    stats = record.decision.aggregation.per_configuration["agent"]
    assert stats.n_cells == 3
    assert stats.pass_rate == 1.0
    assert stats.pass_at_k == {1: 1.0, 2: 1.0, 3: 1.0}
    assert "low_sample" not in stats.caveats


def test_process_trace_ref_is_persisted_and_cost_unavailable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MICRO_EVAL_SECRET_TRACE", "trace-secret-value")
    task = TaskSpec(id="trace-task", name="Trace task", input_payload="")
    config = ProjectConfigV2(
        project_name="trace-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(
                    name="agent",
                    command=[sys.executable, "-c", "import os; print(os.environ['MICRO_EVAL_SECRET_TRACE'])"],
                    required_secrets=["MICRO_EVAL_SECRET_TRACE"],
                ),
            )
        ],
    )
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    run_dir = tmp_path / ".micro-eval" / "runs" / record.id
    persisted_json = "\n".join(path.read_text(errors="ignore") for path in run_dir.rglob("*.json"))

    assert record.traces
    assert record.traces[0].provider == "process"
    assert record.traces[0].cost is not None
    assert record.traces[0].cost.source == "unavailable"
    assert record.results[0].trace_refs == [f"process:{record.results[0].cell_id}"]
    assert record.decision is not None
    assert record.decision.aggregation.per_configuration["agent"].total_cost is not None
    assert record.decision.aggregation.per_configuration["agent"].total_cost.source == "unavailable"
    assert "trace-secret-value" not in persisted_json
    assert "[REDACTED:MICRO_EVAL_SECRET_TRACE]" in persisted_json


def test_llm_judge_does_not_override_deterministic_validation_failure(tmp_path: Path, monkeypatch) -> None:
    from micro_eval.evaluation.llm_judge import JudgeOutcome
    import micro_eval.engine.kernel as kernel_module

    class PassingJudge:
        name = "fake-judge"

        def judge(self, *, prompt, cell, result, config):  # noqa: ANN001
            return JudgeOutcome(score=1.0, pass_fail="pass", rationale="judge liked it", scores={"overall": 1.0})

    monkeypatch.setattr(kernel_module, "resolve_judge_client", lambda _config: PassingJudge())
    task = TaskSpec(
        id="judge-task",
        name="Judge task",
        input_payload="",
        rubric="Score task alignment",
        expectations=[{"type": "contains", "value": "expected", "stream": "stdout"}],
    )
    config = ProjectConfigV2(
        project_name="judge-test",
        configurations=[
            ConfigurationSpec(
                id="agent",
                name="agent",
                agent=AgentSpec(name="agent", command=[sys.executable, "-c", "print('actual')"]),
            )
        ],
    )
    config.judge.enabled = True
    config.config_hash = "config-hash"
    plan = build_run_plan(config, [task], project_root=tmp_path)

    record = asyncio.run(ExecutionKernel(tmp_path).run(plan))
    result = record.results[0]

    assert result.pass_fail == "fail"
    assert result.status.value == "fail"
    assert any("::llm-judge::" in ref for ref in result.evaluation_refs)
    assert any(item.kind == "judge_rationale" for item in record.evidence)
    assert record.decision is not None
    assert record.decision.verdict.value != "improved"
