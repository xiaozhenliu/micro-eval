"""Boundary and edge-case tests for ArtifactStore."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from micro_eval.models.artifact import EvidenceItem, TraceRef
from micro_eval.store.artifact_store import ArtifactStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path, **kwargs) -> ArtifactStore:
    run_dir = tmp_path / "run-test"
    return ArtifactStore(run_dir, **kwargs)


# ---------------------------------------------------------------------------
# manifest.json missing → new manifest created
# ---------------------------------------------------------------------------

def test_missing_manifest_creates_new_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-fresh"
    run_dir.mkdir(parents=True)
    manifest_path = run_dir / "manifest.json"
    # Ensure the manifest file does NOT exist before construction
    assert not manifest_path.exists()

    store = ArtifactStore(run_dir)

    # After construction, manifest must be written and have the correct run_id
    assert manifest_path.exists()
    assert store.manifest.run_id == "run-fresh"
    assert store.manifest.artifacts == []


# ---------------------------------------------------------------------------
# manifest.json corrupted (invalid JSON) → ValidationError propagates
# ---------------------------------------------------------------------------

def test_corrupted_manifest_raises_on_load(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-corrupt"
    run_dir.mkdir(parents=True)
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text("{not valid json!!!")

    # The store should raise during __init__ because _load_manifest calls
    # Manifest.model_validate_json which fails on invalid JSON.
    with pytest.raises(Exception):
        ArtifactStore(run_dir)


# ---------------------------------------------------------------------------
# Artifact exceeding size cap → skipped_oversized warning
# ---------------------------------------------------------------------------

def test_oversized_artifact_is_rejected(tmp_path: Path) -> None:
    cap = 100  # tiny cap for the test
    store = ArtifactStore(tmp_path / "run-oversized", artifact_cap_bytes=cap)

    cell_dir = store.cell_dir("cell-1")
    big_file = cell_dir / "big.txt"
    big_file.write_bytes(b"x" * (cap + 1))  # one byte over the cap

    ref = store.index_file("cell-1", "output", big_file)

    assert ref.warning == "skipped_oversized"
    assert ref.sha256 == ""
    assert ref.size_bytes == cap + 1


# ---------------------------------------------------------------------------
# Artifact within size cap → indexed normally
# ---------------------------------------------------------------------------

def test_normal_artifact_is_indexed(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cell_dir = store.cell_dir("cell-2")
    small_file = cell_dir / "out.txt"
    small_file.write_text("hello world")

    ref = store.index_file("cell-2", "output", small_file)

    assert ref.warning is None
    assert ref.sha256 != ""
    assert ref.size_bytes == len("hello world")
    assert ref.media_type == "text/plain"
    # non-binary content should be marked as redacted=True
    assert ref.redacted is True


# ---------------------------------------------------------------------------
# Symlink artifact → linked_artifact_skipped warning (lines 40-53)
# ---------------------------------------------------------------------------

def test_symlink_artifact_is_skipped(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cell_dir = store.cell_dir("cell-sym")

    real_file = cell_dir / "real.txt"
    real_file.write_text("data")
    link_file = cell_dir / "link.txt"
    link_file.symlink_to(real_file)

    ref = store.index_file("cell-sym", "output", link_file)

    assert ref.warning == "linked_artifact_skipped"
    assert ref.sha256 == ""
    assert ref.size_bytes == 0


# ---------------------------------------------------------------------------
# Binary artifact → binary_redaction_skipped warning, redacted=False
# ---------------------------------------------------------------------------

def test_binary_artifact_gets_warning(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cell_dir = store.cell_dir("cell-bin")
    bin_file = cell_dir / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03")  # NUL byte → binary

    ref = store.index_file("cell-bin", "output", bin_file)

    assert ref.warning == "binary_redaction_skipped"
    assert ref.redacted is False
    assert ref.media_type == "application/octet-stream"


# ---------------------------------------------------------------------------
# write_text round-trip → persists to disk and manifest
# ---------------------------------------------------------------------------

def test_write_text_persists_artifact(tmp_path: Path) -> None:
    store = _make_store(tmp_path)

    ref = store.write_text("cell-wt", "stdout", "output.txt", "some output")

    out_path = (tmp_path / "run-test" / "cells" / "cell-wt" / "output.txt")
    assert out_path.exists()
    assert out_path.read_text() == "some output"
    assert ref.sha256 != ""
    assert any(a.artifact_id == ref.artifact_id for a in store.manifest.artifacts)


# ---------------------------------------------------------------------------
# add_evidence → persisted in manifest
# ---------------------------------------------------------------------------

def test_add_evidence_updates_manifest(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    evidence = EvidenceItem(
        evidence_id="ev-1",
        kind="validator",
        summary="All checks passed",
    )
    store.add_evidence(evidence)

    # Reload the manifest from disk to verify persistence
    store2 = ArtifactStore(tmp_path / "run-test")
    assert any(e.evidence_id == "ev-1" for e in store2.manifest.evidence)


# ---------------------------------------------------------------------------
# add_trace → persisted in manifest, deduplicates by (trace_id, provider)
# ---------------------------------------------------------------------------

def test_add_trace_deduplicates(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    trace = TraceRef(trace_id="tr-1", provider="process")
    store.add_trace(trace)
    store.add_trace(trace)  # duplicate

    assert len(store.manifest.traces) == 1


# ---------------------------------------------------------------------------
# index_existing_outputs → skips reserved filenames and directories
# ---------------------------------------------------------------------------

def test_index_existing_outputs_skips_reserved_files(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cell_dir = store.cell_dir("cell-idx")

    (cell_dir / "result.json").write_text('{"ok": true}')
    (cell_dir / "evaluation.json").write_text('{"score": 1}')
    (cell_dir / "output.txt").write_text("real output")

    refs = store.index_existing_outputs("cell-idx")

    paths = [r.path for r in refs]
    # reserved files must not appear
    assert not any("result.json" in p for p in paths)
    assert not any("evaluation.json" in p for p in paths)
    # regular file must appear
    assert any("output.txt" in p for p in paths)


# ---------------------------------------------------------------------------
# index_existing_outputs with exclude_names
# ---------------------------------------------------------------------------

def test_index_existing_outputs_respects_exclude_names(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cell_dir = store.cell_dir("cell-excl")
    (cell_dir / "keep.txt").write_text("keep me")
    (cell_dir / "skip.txt").write_text("skip me")

    refs = store.index_existing_outputs("cell-excl", exclude_names={"skip.txt"})

    paths = [r.path for r in refs]
    assert any("keep.txt" in p for p in paths)
    assert not any("skip.txt" in p for p in paths)


# ---------------------------------------------------------------------------
# manifest reloaded correctly from an existing file (line 134)
# ---------------------------------------------------------------------------

def test_existing_manifest_is_loaded(tmp_path: Path) -> None:
    # First store writes a manifest
    store1 = _make_store(tmp_path)
    store1.write_text("cell-x", "stdout", "out.txt", "hello")

    # Second store opening the same directory should load the existing manifest
    store2 = ArtifactStore(tmp_path / "run-test")
    assert len(store2.manifest.artifacts) == 1
