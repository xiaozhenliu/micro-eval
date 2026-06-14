"""Artifact persistence and manifest indexing."""

from __future__ import annotations

import stat
import uuid
from pathlib import Path

from micro_eval.models.artifact import ArtifactRef, EvidenceItem, Manifest, TraceRef
from micro_eval.models.ids import looks_binary, safe_path_segment, sha256_bytes


class ArtifactStore:
    """Write artifacts under one canonical run directory."""

    def __init__(self, run_dir: Path, *, artifact_cap_bytes: int = 10 * 1024 * 1024):
        self.run_dir = run_dir
        self.artifact_cap_bytes = artifact_cap_bytes
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.run_dir / "manifest.json"
        self.manifest = self._load_manifest()

    def cell_dir(self, cell_id: str) -> Path:
        """Return the canonical cell directory."""
        path = self.run_dir / "cells" / safe_path_segment(cell_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_text(self, cell_id: str, kind: str, filename: str, text: str) -> ArtifactRef:
        """Persist a text artifact and update manifest."""
        path = self.cell_dir(cell_id) / filename
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(text)
        tmp.replace(path)
        return self.index_file(cell_id, kind, path)

    def index_file(self, cell_id: str, kind: str, path: Path) -> ArtifactRef:
        """Add an existing file to the manifest."""
        file_stat = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink > 1:
            path.unlink(missing_ok=True)
            artifact = ArtifactRef(
                artifact_id=f"{cell_id}::{kind}::skipped-{sha256_bytes(str(path).encode())[:12]}",
                kind=kind,
                path=str(path.relative_to(self.run_dir)),
                sha256="",
                size_bytes=0,
                media_type="application/octet-stream",
                redacted=False,
                warning="linked_artifact_skipped",
            )
            self._upsert_artifact(artifact)
            return artifact
        if file_stat.st_size > self.artifact_cap_bytes:
            artifact = ArtifactRef(
                artifact_id=f"{cell_id}::{kind}::skipped-{sha256_bytes(str(path).encode())[:12]}",
                kind=kind,
                path=str(path.relative_to(self.run_dir)),
                sha256="",
                size_bytes=file_stat.st_size,
                media_type="application/octet-stream",
                redacted=False,
                warning="skipped_oversized",
            )
            self._upsert_artifact(artifact)
            return artifact
        data = path.read_bytes()
        digest = sha256_bytes(data)
        warnings: list[str] = []
        is_binary = looks_binary(data)
        if is_binary:
            warnings.append("binary_redaction_skipped")
        artifact = ArtifactRef(
            artifact_id=f"{cell_id}::{kind}::{digest[:12]}",
            kind=kind,
            path=str(path.relative_to(self.run_dir)),
            sha256=digest,
            size_bytes=len(data),
            media_type="application/octet-stream" if is_binary else "text/plain",
            redacted=not is_binary,
            warning=";".join(warnings) if warnings else None,
        )
        self._upsert_artifact(artifact)
        return artifact

    def index_existing_outputs(self, cell_id: str, *, exclude_names: set[str] | None = None) -> list[ArtifactRef]:
        """Index output files already written by directory-mode agents."""
        excluded = exclude_names or set()
        artifacts: list[ArtifactRef] = []
        root = self.cell_dir(cell_id)
        root_real = root.resolve()
        for path in sorted(root.rglob("*")):
            if path.name in excluded:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.name in {"result.json", "evaluation.json"}:
                continue
            try:
                file_stat = path.lstat()
                real_path = path.resolve(strict=True)
            except OSError:
                continue
            if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink > 1 or not _is_relative_to(real_path, root_real):
                path.unlink(missing_ok=True)
                continue
            artifacts.append(self.index_file(cell_id, "file", path))
        return artifacts

    def add_evidence(self, evidence: EvidenceItem) -> EvidenceItem:
        """Add structured evidence and update manifest."""
        existing = [item for item in self.manifest.evidence if item.evidence_id != evidence.evidence_id]
        self.manifest.evidence = existing + [evidence]
        self.save()
        return evidence

    def add_trace(self, trace: TraceRef) -> TraceRef:
        """Add a normalized trace reference and update manifest."""
        existing = [
            item
            for item in self.manifest.traces
            if not (item.trace_id == trace.trace_id and item.provider == trace.provider)
        ]
        self.manifest.traces = existing + [trace]
        self.save()
        return trace

    def save(self) -> None:
        """Write manifest.json."""
        self.manifest_path.write_text(self.manifest.model_dump_json(indent=2))

    def _load_manifest(self) -> Manifest:
        if self.manifest_path.exists():
            return Manifest.model_validate_json(self.manifest_path.read_text())
        run_id = self.run_dir.name
        manifest = Manifest(run_id=run_id)
        self.manifest_path.write_text(manifest.model_dump_json(indent=2))
        return manifest

    def _upsert_artifact(self, artifact: ArtifactRef) -> None:
        existing = [item for item in self.manifest.artifacts if item.artifact_id != artifact.artifact_id]
        self.manifest.artifacts = existing + [artifact]
        self.save()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
