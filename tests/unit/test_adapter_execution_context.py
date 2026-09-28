"""Adapter paths, environment, and artifact guarantees across execution contexts."""

from __future__ import annotations

from pathlib import Path

import pytest

from micro_eval.engine.adapter import AdapterError, AgentAdapter, Redactor
from micro_eval.engine.providers.base import CommandResult, ExecutionRequest
from micro_eval.models.configuration import AgentSpec, InputMode, OutputMode


class RemoteContext:
    is_remote = True
    workspace_path = Path("/sandbox/workspace")
    python_executable = "/sandbox/bin/python3"

    def __init__(self) -> None:
        self.request: ExecutionRequest | None = None
        self.files: dict[Path, bytes] = {}

    async def prepare_output(self, host_output_dir: Path) -> Path:
        return Path("/sandbox/output")

    async def write_file(self, path: Path, data: bytes) -> None:
        self.files[path] = data

    async def execute(self, request: ExecutionRequest) -> CommandResult:
        self.request = request
        self.files[Path("/sandbox/output/output.txt")] = b"answer"
        return CommandResult(exit_code=0)

    async def collect_output(self, remote_output: Path, host_output: Path, byte_limit: int) -> bool:
        assert remote_output == Path("/sandbox/output")
        for path, data in self.files.items():
            (host_output / path.name).write_bytes(data[:byte_limit])
        return False


async def test_remote_paths_python_and_environment_are_resolved_at_execution_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT"):
        monkeypatch.setenv(key, "/host-only")
    monkeypatch.setenv("MICRO_EVAL_SECRET_E2B_API_KEY", "control-key")
    monkeypatch.setenv("MICRO_EVAL_SECRET_APP", "application-key")
    context = RemoteContext()
    result, _ = await AgentAdapter().invoke(
        agent=AgentSpec(
            name="remote", command=["{python}", "agent.py", "{input_file}", "{output_file}", "{output_dir}"],
            input_mode=InputMode.file, output_mode=OutputMode.file,
            required_secrets=["MICRO_EVAL_SECRET_APP"],
        ),
        input_payload="question", cwd=tmp_path, output_dir=tmp_path / "output",
        execution_context=context,
    )
    assert context.request is not None
    assert context.request.cwd == Path("/sandbox/workspace")
    assert context.request.argv == [
        "/sandbox/bin/python3", "agent.py", "/sandbox/output/input.txt",
        "/sandbox/output/output.txt", "/sandbox/output",
    ]
    assert context.request.stdin is None
    assert context.files[Path("/sandbox/output/input.txt")] == b"question"
    assert context.request.env is not None
    assert context.request.env["MICRO_EVAL_SECRET_APP"] == "application-key"
    assert not {"PATH", "HOME", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "MICRO_EVAL_SECRET_E2B_API_KEY"}.intersection(context.request.env)
    assert result.output == "answer"
    assert result.output_artifacts == [str(tmp_path / "output" / "output.txt")]


@pytest.mark.parametrize("name", [
    "E2B_API_KEY", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
    "MICRO_EVAL_SECRET_E2B_API_KEY", "MICRO_EVAL_SECRET_MODAL_TOKEN_ID",
    "MICRO_EVAL_SECRET_MODAL_TOKEN_SECRET",
])
@pytest.mark.parametrize("source", ["env", "required_secrets"])
def test_provider_control_credentials_cannot_be_declared_as_agent_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, source: str,
) -> None:
    monkeypatch.setenv(name, "secret-control-credential")
    values = {source: {name: "value"} if source == "env" else [name]}
    # Also exercise the execution boundary for callers that construct specs
    # programmatically, bypassing required_secrets' naming validator.
    agent = AgentSpec.model_construct(name="agent", command=["echo"], **values)
    with pytest.raises(AdapterError, match="provider control credentials"):
        AgentAdapter().build_env(agent, tmp_path, tmp_path / "output.txt", "", remote=True)


@pytest.mark.parametrize("cap", [1, 4, 10, 20])
def test_redaction_removes_secret_prefix_at_byte_cap(tmp_path: Path, cap: int) -> None:
    secret = "abcdefghijklmnopqrstuv"
    path = tmp_path / "answer.txt"
    path.write_text(secret + " extra")
    output, truncated = AgentAdapter(output_cap_bytes=cap)._redact_text_file(
        path, Redactor({"MICRO_EVAL_SECRET_TOKEN": secret}),
    )
    assert truncated
    assert secret[:cap] not in output
    assert len(path.read_bytes()) <= cap


def test_redaction_retains_boundary_information_from_remote_collection(tmp_path: Path) -> None:
    secret = "abcdefghijklmnop"
    path = tmp_path / "output.txt"
    path.write_text(secret[:5])
    output, artifacts, truncated, missing = AgentAdapter(output_cap_bytes=5)._select_output(
        AgentSpec(name="agent", command=["echo"], output_mode=OutputMode.file),
        tmp_path, path, "", Redactor({"TOKEN": secret}), collected_truncated=True,
    )
    assert secret[:5] not in output
    assert truncated and not missing
    assert artifacts == [path]


def test_directory_budget_preserves_complete_binary_with_manifest_warning(tmp_path: Path) -> None:
    from micro_eval.store.artifact_store import ArtifactStore

    store = ArtifactStore(tmp_path)
    output_dir = store.cell_dir("cell")
    binary_data = b"secret\x00binary"
    (output_dir / "a.bin").write_bytes(binary_data)
    (output_dir / "b.txt").write_text("b" * 4)
    (output_dir / "c.bin").write_bytes(b"cccc\x00")
    (output_dir / "d.txt").write_text("d" * 16)
    (output_dir / ".tmp").mkdir()
    (output_dir / ".tmp" / "private").write_text("temporary")
    output, artifacts, truncated, missing = AgentAdapter(output_cap_bytes=20)._select_output(
        AgentSpec(name="agent", command=["echo"], output_mode=OutputMode.directory),
        output_dir, output_dir / "output.txt", "", Redactor({}),
    )
    assert truncated and not missing
    assert sum(path.stat().st_size for path in artifacts) <= 20
    assert len(output.encode()) <= 20
    assert (output_dir / "a.bin") in artifacts
    assert (output_dir / "a.bin").read_bytes() == binary_data
    assert (output_dir / "b.txt") in artifacts
    assert (output_dir / "c.bin") not in artifacts
    assert not (output_dir / "c.bin").exists()
    indexed = store.index_existing_outputs("cell", include_paths=artifacts)
    binary = next(artifact for artifact in indexed if artifact.path.endswith("a.bin"))
    assert binary.redacted is False
    assert binary.warning == "binary_redaction_skipped"
    assert binary.size_bytes == len(binary_data)


def test_binary_file_output_survives_text_summary_persistence(tmp_path: Path) -> None:
    from micro_eval.store.artifact_store import ArtifactStore

    store = ArtifactStore(tmp_path)
    output_dir = store.cell_dir("cell")
    output_file = output_dir / "output.txt"
    data = b"binary\x00content"
    output_file.write_bytes(data)
    # Existing agent artifacts must not be overwritten to relocate output.txt.
    (output_dir / "binary-output.bin").write_bytes(b"existing")
    text, artifacts, truncated, missing = AgentAdapter()._select_output(
        AgentSpec(name="agent", command=["echo"], output_mode=OutputMode.file),
        output_dir, output_file, "", Redactor({}),
    )
    assert not truncated and not missing
    assert len(artifacts) == 1 and artifacts[0] != output_file
    store.write_text("cell", "output", "output.txt", text)
    indexed = store.index_existing_outputs(
        "cell", exclude_names={"output.txt"}, include_paths=artifacts,
    )
    assert artifacts[0].read_bytes() == data
    assert (output_dir / "binary-output.bin").read_bytes() == b"existing"
    assert len(indexed) == 1
    assert indexed[0].redacted is False
    assert indexed[0].warning == "binary_redaction_skipped"


def test_oversized_binary_file_is_skipped_without_partial_artifact(tmp_path: Path) -> None:
    output_file = tmp_path / "output.txt"
    output_file.write_bytes(b"a\x00" + b"b" * 100)
    _, artifacts, truncated, missing = AgentAdapter(output_cap_bytes=10)._select_output(
        AgentSpec(name="agent", command=["echo"], output_mode=OutputMode.file),
        tmp_path, output_file, "", Redactor({}),
    )
    assert truncated and not missing
    assert artifacts == []
    assert not output_file.exists()


def test_output_scan_stops_at_global_entry_limit_and_does_not_follow_links(tmp_path: Path) -> None:
    from micro_eval.engine.adapter import _scan_output_paths

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("secret")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "link").symlink_to(outside, target_is_directory=True)
    (output_dir / "inside").mkdir()
    for number in range(10):
        (output_dir / "inside" / str(number)).write_text("value")
    limited, truncated = _scan_output_paths(output_dir, entry_limit=5)
    assert truncated
    assert len(limited) == 5
    assert not any(path.name == "secret" for path in limited)
    complete, truncated = _scan_output_paths(output_dir)
    assert not truncated
    assert len(complete) == 12
    assert not any(path.name == "secret" for path in complete)


def test_file_read_is_bounded_without_path_read_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "large.txt"
    with path.open("wb") as stream:
        stream.truncate(1024 * 1024 * 100)
        stream.seek(0)
        stream.write(b"abcdefghijk")
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("unbounded read"))
    output, truncated = AgentAdapter(output_cap_bytes=8)._redact_text_file(path, Redactor({}))
    assert output == "abcdefgh"
    assert truncated
    assert path.stat().st_size == 8


@pytest.mark.parametrize("mode", [OutputMode.stdout, OutputMode.file])
async def test_unselected_remote_files_never_reach_durable_cell_directory(
    tmp_path: Path, mode: OutputMode,
) -> None:
    context = RemoteContext()
    context.files[Path("/sandbox/output/hidden.txt")] = b"raw-unselected-secret"
    output_dir = tmp_path / "cell"
    result, _ = await AgentAdapter().invoke(
        agent=AgentSpec(name="agent", command=["echo"], output_mode=mode),
        input_payload="private input", cwd=tmp_path, output_dir=output_dir,
        execution_context=context,
    )
    assert not (output_dir / "hidden.txt").exists()
    assert not (output_dir / "input.txt").exists()
    assert not list(tmp_path.glob(".micro-eval-receive-*"))
    assert len(result.output_artifacts) == (1 if mode == OutputMode.file else 0)


async def test_cancelled_collection_removes_all_received_raw_files(tmp_path: Path) -> None:
    import asyncio

    class CancelContext(RemoteContext):
        async def collect_output(self, remote_output, host_output, byte_limit):
            (host_output / "private.txt").write_text("raw-private-secret")
            raise asyncio.CancelledError

    output_dir = tmp_path / "cell"
    with pytest.raises(asyncio.CancelledError):
        await AgentAdapter().invoke(
            agent=AgentSpec(name="agent", command=["echo"], output_mode=OutputMode.directory),
            input_payload="private input", cwd=tmp_path, output_dir=output_dir,
            execution_context=CancelContext(),
        )
    assert list(output_dir.iterdir()) == []
    assert not list(tmp_path.glob(".micro-eval-receive-*"))


async def test_direct_invoke_discards_unselected_raw_files(tmp_path: Path) -> None:
    import sys

    output_dir = tmp_path / "cell"
    code = (
        "import os, pathlib; "
        "pathlib.Path(os.environ['MICRO_EVAL_OUTPUT_DIR'], 'private.txt').write_text('raw-secret'); "
        "print('answer')"
    )
    result, _ = await AgentAdapter().invoke(
        agent=AgentSpec(name="agent", command=[sys.executable, "-c", code]),
        input_payload="private input", cwd=tmp_path, output_dir=output_dir,
    )
    assert result.output == "answer\n"
    assert list(output_dir.iterdir()) == []
    assert not list(tmp_path.glob(".micro-eval-execute-*"))
    assert not list(tmp_path.glob(".micro-eval-receive-*"))


def test_oversized_artifact_with_binary_tail_is_not_retained_as_partial(tmp_path: Path) -> None:
    output_file = tmp_path / "output.txt"
    output_file.write_bytes(b"prefix" * 100 + b"\x00")
    _, artifacts, truncated, missing = AgentAdapter(output_cap_bytes=10)._select_output(
        AgentSpec(name="agent", command=["echo"], output_mode=OutputMode.file),
        tmp_path, output_file, "", Redactor({}),
    )
    assert truncated and not missing
    assert artifacts == []
    assert not output_file.exists()


async def test_secret_in_agent_filename_is_removed_from_results_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    from micro_eval.store.artifact_store import ArtifactStore

    secret = "private-filename-token"
    monkeypatch.setenv("MICRO_EVAL_SECRET_FILENAME", secret)
    # A secret in the user-owned root is a real path, not an agent filename.
    store = ArtifactStore(tmp_path / secret)
    output_dir = store.cell_dir("cell")
    code = (
        "import os, pathlib; root = pathlib.Path(os.environ['MICRO_EVAL_OUTPUT_DIR']); "
        "token = os.environ['MICRO_EVAL_SECRET_FILENAME']; "
        "(root / token).mkdir(); (root / token / 'answer.txt').write_text('answer'); "
        "(root / ('prefix-' + token + '.bin')).write_bytes(b'blob\\x00body'); "
        "(root / 'ordinary.txt').write_text('ordinary')"
    )
    result, _ = await AgentAdapter().invoke(
        agent=AgentSpec(
            name="agent", command=[sys.executable, "-c", code],
            output_mode=OutputMode.directory, required_secrets=["MICRO_EVAL_SECRET_FILENAME"],
        ),
        input_payload="", cwd=tmp_path, output_dir=output_dir,
    )
    assert len(result.output_artifacts) == 3
    relative_paths = [Path(path).relative_to(output_dir) for path in result.output_artifacts]
    assert all(secret not in str(path) for path in relative_paths)
    assert Path("ordinary.txt") in relative_paths
    assert len([path for path in relative_paths if path.name.startswith("redacted-artifact-")]) == 2
    artifacts = store.index_existing_outputs("cell", include_paths=result.output_artifacts)
    assert all(secret not in artifact.path for artifact in artifacts)
    assert any(artifact.warning == "binary_redaction_skipped" for artifact in artifacts)
    assert not (output_dir / secret).exists()
