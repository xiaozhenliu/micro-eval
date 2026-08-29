from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[2] / "scripts" / "release" / "public_projection.py"
)
PROJECT_ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location("public_projection", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
public_projection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = public_projection
SPEC.loader.exec_module(public_projection)


def _run(argv: list[str], cwd: Path) -> None:
    subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "--initial-branch=dev"], repo)
    _run(["git", "config", "user.name", "Policy Test"], repo)
    _run(["git", "config", "user.email", "policy@example.invalid"], repo)
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "fixture"], repo)
    return repo


def _write_policy(tmp_path: Path, *, public: str, private: str, forbidden: str) -> Path:
    path = tmp_path / "policy.toml"
    private_key_marker = "-----BEGIN OPENSSH " "PRIVATE KEY-----"
    path.write_text(
        f'''version = 1
[paths]
public = ["{public}"]
private = ["{private}"]
required_public = []
forbidden_public = ["{forbidden}"]
forbidden_content_markers = ["{private_key_marker}"]
[artifacts]
sdist = ["src/**", "PKG-INFO"]
wheel = ["micro_eval/**", "micro_eval-*.dist-info/**"]
''',
        encoding="utf-8",
    )
    return path


def test_policy_rejects_overlapping_public_and_private_classification(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path, {"docs/private/note.md": "internal\n"})
    policy = public_projection.ProjectionPolicy.load(
        _write_policy(
            tmp_path,
            public="docs/**",
            private="docs/private/**",
            forbidden="never/**",
        )
    )

    with pytest.raises(public_projection.ProjectionError, match="public/private"):
        policy.plan(repo, "HEAD")


def test_policy_rejects_sensitive_path_even_when_public(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"config/.env": "SECRET=value\n"})
    policy = public_projection.ProjectionPolicy.load(
        _write_policy(
            tmp_path,
            public="config/**",
            private="private/**",
            forbidden="**/.env",
        )
    )

    with pytest.raises(public_projection.ProjectionError, match="forbidden public"):
        policy.plan(repo, "HEAD")


def test_policy_accepts_brackets_in_concrete_git_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path, {"src/app/[jobId]/route.py": "value = 1\n"})
    policy = public_projection.ProjectionPolicy.load(
        _write_policy(
            tmp_path,
            public="src/**",
            private="private/**",
            forbidden="never/**",
        )
    )

    plan = policy.plan(repo, "HEAD")

    assert plan.public_paths == ("src/app/[jobId]/route.py",)


def test_candidate_scan_rejects_private_key_marker(tmp_path: Path) -> None:
    private_key_marker = "-----BEGIN OPENSSH " "PRIVATE KEY-----"
    repo = _init_repo(tmp_path, {"src/key.txt": f"{private_key_marker}\n"})
    policy = public_projection.ProjectionPolicy.load(
        _write_policy(
            tmp_path,
            public="src/**",
            private="private/**",
            forbidden="never/**",
        )
    )

    with pytest.raises(public_projection.ProjectionError, match="private-key marker"):
        public_projection._scan_candidate(policy, repo, ("src/key.txt",))


def test_project_policy_keeps_scratch_private_and_forbidden() -> None:
    policy = public_projection.ProjectionPolicy.load(
        PROJECT_ROOT / "scripts/release/public-projection.toml"
    )
    probe = ".scratch/governance-probe.md"

    assert public_projection._matches_any(probe, policy.private_patterns)
    assert not public_projection._matches_any(probe, policy.public_patterns)
    assert public_projection._matches_any(probe, policy.forbidden_public)


def test_artifact_verifier_rejects_unknown_sdist_entry(tmp_path: Path) -> None:
    policy = public_projection.ProjectionPolicy.load(
        _write_policy(
            tmp_path,
            public="src/**",
            private="private/**",
            forbidden="never/**",
        )
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    version = "1.2.3"
    with tarfile.open(dist / f"micro_eval-{version}.tar.gz", "w:gz") as archive:
        for name in ("src/micro_eval/__init__.py", "local-session.log", "PKG-INFO"):
            content = b"test\n"
            info = tarfile.TarInfo(f"micro_eval-{version}/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    with zipfile.ZipFile(
        dist / f"micro_eval-{version}-py3-none-any.whl", "w"
    ) as archive:
        archive.writestr("micro_eval/__init__.py", "")
        archive.writestr(f"micro_eval-{version}.dist-info/METADATA", "")

    with pytest.raises(public_projection.ProjectionError, match="local-session.log"):
        public_projection.verify_artifacts(policy, dist, version)


@pytest.mark.parametrize("entry", ["../secret", "/absolute/secret"])
def test_artifact_verifier_rejects_unsafe_archive_path(entry: str) -> None:
    with pytest.raises(public_projection.ProjectionError, match="unsafe archive path"):
        public_projection._safe_archive_path(entry)


def test_artifact_verifier_rejects_sdist_link(tmp_path: Path) -> None:
    policy = public_projection.ProjectionPolicy.load(
        _write_policy(
            tmp_path,
            public="src/**",
            private="private/**",
            forbidden="never/**",
        )
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    version = "1.2.3"
    with tarfile.open(dist / f"micro_eval-{version}.tar.gz", "w:gz") as archive:
        link = tarfile.TarInfo(
            f"micro_eval-{version}/src/micro_eval/linked-secret"
        )
        link.type = tarfile.SYMTYPE
        link.linkname = "../../private/secret"
        archive.addfile(link)
    with zipfile.ZipFile(
        dist / f"micro_eval-{version}-py3-none-any.whl", "w"
    ) as archive:
        archive.writestr("micro_eval/__init__.py", "")

    with pytest.raises(public_projection.ProjectionError, match="links are forbidden"):
        public_projection.verify_artifacts(policy, dist, version)


def test_artifact_verifier_rejects_wheel_link(tmp_path: Path) -> None:
    policy = public_projection.ProjectionPolicy.load(
        _write_policy(
            tmp_path,
            public="src/**",
            private="private/**",
            forbidden="never/**",
        )
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    version = "1.2.3"
    with tarfile.open(dist / f"micro_eval-{version}.tar.gz", "w:gz") as archive:
        content = b"test\n"
        for name in ("src/micro_eval/__init__.py", "PKG-INFO"):
            info = tarfile.TarInfo(f"micro_eval-{version}/{name}")
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    with zipfile.ZipFile(
        dist / f"micro_eval-{version}-py3-none-any.whl", "w"
    ) as archive:
        link = zipfile.ZipInfo("micro_eval/linked-secret")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive.writestr(link, "../private/secret")

    with pytest.raises(public_projection.ProjectionError, match="links are forbidden"):
        public_projection.verify_artifacts(policy, dist, version)
