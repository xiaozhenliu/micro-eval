"""Unified binary-detection tests (issue #12).

The adapter (text redaction skip) and the artifact store (media type +
``redacted`` flag) must classify the same bytes identically. Previously the
artifact store only inspected the first 1024 bytes, so a binary file with its
first NUL byte past that offset was mislabelled as text and marked redacted.
"""

from __future__ import annotations

from pathlib import Path

from micro_eval.models.ids import looks_binary
from micro_eval.store.artifact_store import ArtifactStore


def test_looks_binary_scans_whole_buffer() -> None:
    assert looks_binary(b"hello\x00world")
    # NUL byte well past the old 1024-byte window must still be detected.
    assert looks_binary(b"a" * 2000 + b"\x00")
    assert not looks_binary(b"plain text content")
    assert not looks_binary(b"")


def test_artifact_store_classifies_late_null_byte_as_binary(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "run")
    path = store.cell_dir("cell-1") / "out.bin"
    path.write_bytes(b"a" * 2000 + b"\x00" + b"b" * 10)  # NUL at offset 2000

    ref = store.index_file("cell-1", "stdout", path)

    assert ref.media_type == "application/octet-stream"
    assert ref.redacted is False
    assert ref.warning is not None and "binary_redaction_skipped" in ref.warning


def test_artifact_store_keeps_plain_text_redactable(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "run")
    path = store.cell_dir("cell-1") / "out.txt"
    path.write_bytes(b"plain text line\n" * 200)  # > 1024 bytes, no NUL

    ref = store.index_file("cell-1", "stdout", path)

    assert ref.media_type == "text/plain"
    assert ref.redacted is True
