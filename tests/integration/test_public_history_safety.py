from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).parents[2]
VERSION = "1.2.3"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def projection() -> ModuleType:
    name = "public_projection_history_safety_tests"
    spec = importlib.util.spec_from_file_location(
        name, PROJECT_ROOT / "scripts/release/public_projection.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class PublicRepo:
    path: Path
    policy_path: Path
    base: str
    source: str
    dist: Path
    origin: Path

    def receipt_path(self, sha: str) -> Path:
        return self.path / ".git/micro-eval-release/receipts" / f"{sha}.json"

    def write_receipt(self, receipt: dict[str, Any]) -> None:
        path = self.receipt_path(receipt["candidate_sha"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt), encoding="utf-8")


@pytest.fixture
def public_repo(tmp_path: Path) -> PublicRepo:
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "Release test")
    _git(repo, "config", "user.email", "release@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")
    _write(repo, "README.md", "Public base\n")
    _write(repo, "VERSION", VERSION + "\n")
    _write(repo, "AGENTS.md", "Public instructions\n")
    base = _commit(repo, "public baseline")
    _git(repo, "checkout", "-b", "dev")
    _write(repo, "README.md", "Released public source\n")
    _write(repo, ".private/AGENTS.md", "Public instructions\n")
    _write(repo, ".private/source.txt", "Private development evidence\n")
    source = _commit(repo, "private development source")

    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(
        f'''version = 1

[history]
public_base_sha = "{base}"

[paths]
public = ["README.md", "VERSION", "public/**"]
private = [".private/**"]
required_public = ["README.md", "VERSION", "AGENTS.md"]
forbidden_public = [".private/**"]
forbidden_content_markers = ["FORBIDDEN_PRIVATE_MARKER"]

[[generated]]
source = ".private/AGENTS.md"
target = "AGENTS.md"

[artifacts]
sdist = ["README.md"]
wheel = ["micro_eval/__init__.py"]
''',
        encoding="utf-8",
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    with tarfile.open(dist / f"micro_eval-{VERSION}.tar.gz", "w:gz") as archive:
        content = b"Public package\n"
        info = tarfile.TarInfo(f"micro_eval-{VERSION}/README.md")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    with zipfile.ZipFile(
        dist / f"micro_eval-{VERSION}-py3-none-any.whl", "w"
    ) as archive:
        archive.writestr("micro_eval/__init__.py", "")
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "origin", "main")
    return PublicRepo(repo, policy_path, base, source, dist, origin)


def _stage(projection: ModuleType, repo: PublicRepo) -> tuple[Any, dict[str, Any]]:
    policy = projection.ProjectionPolicy.load(repo.policy_path)
    receipt = projection.project_public_tree(repo.path, policy, "dev", "main", VERSION)
    return policy, receipt


def _verify(projection: ModuleType, repo: PublicRepo, policy: Any, sha: str) -> Any:
    return projection.verify_projection(
        repo.path, policy, sha, "main", repo.dist, VERSION
    )


def _changed_commit(
    repo: PublicRepo, source: str, change: str, *, parent: str
) -> str:
    worktree = repo.path.parent / "changed-tree"
    _git(repo.path, "worktree", "add", "--detach", str(worktree), source)
    try:
        if change == "content":
            _write(worktree, "README.md", "Unverified public content\n")
        elif change == "mode":
            (worktree / "README.md").chmod(0o755)
        elif change == "generated":
            _write(worktree, "AGENTS.md", "Unverified generated instructions\n")
        elif change == "additional":
            _write(worktree, "public/unverified.txt", "Unverified addition\n")
        elif change == "symlink":
            (worktree / "README.md").unlink()
            (worktree / "README.md").symlink_to("VERSION")
        else:
            raise AssertionError(f"unknown test change: {change}")
        _git(worktree, "add", "-A")
        tree = _git(worktree, "write-tree")
        message = _git(repo.path, "show", "-s", "--format=%B", source)
        return _git(
            repo.path, "commit-tree", tree, "-p", parent, "-m", message
        )
    finally:
        _git(repo.path, "worktree", "remove", "--force", str(worktree))


def test_projection_has_one_public_parent_and_no_source_ancestry(
    projection: ModuleType, public_repo: PublicRepo
) -> None:
    policy, receipt = _stage(projection, public_repo)
    candidate = receipt["candidate_sha"]
    assert _git(public_repo.path, "show", "-s", "--format=%P", candidate) == public_repo.base
    assert receipt["receipt_version"] == 2
    assert receipt["projection_mode"] == "single-parent"
    assert receipt["source_sha"] == public_repo.source
    assert receipt["history_base_sha"] == public_repo.base
    assert receipt["publication_base_sha"] == public_repo.base
    assert receipt["candidate_tree_sha"] == _git(
        public_repo.path, "rev-parse", f"{candidate}^{{tree}}"
    )
    reachable = _git(public_repo.path, "rev-list", candidate).splitlines()
    assert public_repo.source not in reachable
    projection.verify_public_history(
        public_repo.path, policy, candidate, expected_parent=public_repo.base
    )
    assert _verify(projection, public_repo, policy, candidate)["status"] == "verified"
    assert _git(public_repo.path, "rev-parse", "main") == candidate


def test_history_rejects_clean_tip_after_private_intermediate_commit(
    projection: ModuleType, public_repo: PublicRepo
) -> None:
    _git(public_repo.path, "checkout", "main")
    _write(public_repo.path, ".private/historical.txt", "Private historical evidence\n")
    _commit(public_repo.path, "leak private history")
    _git(public_repo.path, "rm", ".private/historical.txt")
    tip = _commit(public_repo.path, "clean final public tree")
    assert ".private/" not in _git(public_repo.path, "ls-tree", "-r", "--name-only", tip)
    policy = projection.ProjectionPolicy.load(public_repo.policy_path)
    with pytest.raises(projection.ProjectionError):
        projection.verify_public_history(public_repo.path, policy, tip)


def test_history_rejects_clean_merge_with_private_dev_parent(
    projection: ModuleType, public_repo: PublicRepo
) -> None:
    tree = _git(public_repo.path, "rev-parse", f"{public_repo.base}^{{tree}}")
    merge = _git(
        public_repo.path,
        "commit-tree",
        tree,
        "-p",
        public_repo.base,
        "-p",
        public_repo.source,
        "-m",
        "clean tree with private second parent",
    )
    policy = projection.ProjectionPolicy.load(public_repo.policy_path)
    with pytest.raises(projection.ProjectionError):
        projection.verify_public_history(
            public_repo.path, policy, merge, expected_parent=public_repo.base
        )


@pytest.mark.parametrize("change", ["private-marker", "unsafe-symlink", "unknown-path"])
def test_history_scans_intermediate_trees_before_clean_tip(
    projection: ModuleType, public_repo: PublicRepo, change: str
) -> None:
    _git(public_repo.path, "checkout", "main")
    if change == "private-marker":
        _write(public_repo.path, "README.md", "FORBIDDEN_PRIVATE_MARKER\n")
        changed_path = "README.md"
    elif change == "unsafe-symlink":
        (public_repo.path / "README.md").unlink()
        (public_repo.path / "README.md").symlink_to("../private-secret")
        changed_path = "README.md"
    else:
        _write(public_repo.path, "unclassified.txt", "Unknown historical path\n")
        changed_path = "unclassified.txt"
    _commit(public_repo.path, "unsafe intermediate public tree")
    if change == "unknown-path":
        _git(public_repo.path, "rm", changed_path)
    else:
        _git(public_repo.path, "checkout", public_repo.base, "--", changed_path)
    tip = _commit(public_repo.path, "restore clean public tree")
    policy = projection.ProjectionPolicy.load(public_repo.policy_path)
    with pytest.raises(projection.ProjectionError):
        projection.verify_public_history(public_repo.path, policy, tip)


def test_history_requires_explicit_public_base(
    projection: ModuleType, public_repo: PublicRepo
) -> None:
    content = public_repo.policy_path.read_text(encoding="utf-8")
    public_repo.policy_path.write_text(
        content.replace(f'[history]\npublic_base_sha = "{public_repo.base}"\n', ""),
        encoding="utf-8",
    )
    with pytest.raises(projection.ProjectionError):
        policy = projection.ProjectionPolicy.load(public_repo.policy_path)
        projection.verify_public_history(public_repo.path, policy, public_repo.base)


@pytest.mark.parametrize("override", ["replace", "grafts", "shallow"])
def test_history_rejects_local_graph_overrides(
    projection: ModuleType, public_repo: PublicRepo, override: str
) -> None:
    if override == "replace":
        _git(public_repo.path, "replace", public_repo.source, public_repo.base)
    elif override == "grafts":
        _write(public_repo.path, ".git/info/grafts", public_repo.base + "\n")
    else:
        _write(public_repo.path, ".git/shallow", public_repo.base + "\n")
    with pytest.raises(projection.ProjectionError):
        policy = projection.ProjectionPolicy.load(public_repo.policy_path)
        projection.verify_public_history(public_repo.path, policy, public_repo.base)


@pytest.mark.parametrize(
    "field",
    [
        "receipt_version",
        "projection_mode",
        "candidate_sha",
        "candidate_ref",
        "candidate_tree_sha",
        "public_count",
        "policy_document",
        "source_sha",
        "previous_target_sha",
        "history_base_sha",
        "publication_base_sha",
    ],
)
def test_verification_rejects_tampered_receipt_without_moving_main(
    projection: ModuleType, public_repo: PublicRepo, field: str
) -> None:
    policy, receipt = _stage(projection, public_repo)
    candidate = receipt["candidate_sha"]
    changes = {
        "receipt_version": 1,
        "projection_mode": "merge",
        "candidate_sha": public_repo.base,
        "candidate_ref": "refs/heads/dev",
        "candidate_tree_sha": _git(public_repo.path, "rev-parse", f"{public_repo.base}^{{tree}}"),
        "public_count": receipt["public_count"] + 1,
        "policy_document": receipt["policy_document"] + "\n# unverified change\n",
        "source_sha": _changed_commit(
            public_repo, public_repo.source, "content", parent=public_repo.source
        ),
        "previous_target_sha": public_repo.source,
        "history_base_sha": public_repo.source,
        "publication_base_sha": public_repo.source,
    }
    receipt[field] = changes[field]
    public_repo.receipt_path(candidate).write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(projection.ProjectionError):
        _verify(projection, public_repo, policy, candidate)
    assert _git(public_repo.path, "rev-parse", "main") == public_repo.base
    assert _git(public_repo.path, "rev-parse", "dev") == public_repo.source


@pytest.mark.parametrize("change", ["content", "mode", "generated", "additional", "symlink"])
def test_verification_recomputes_source_projection_for_forged_clean_candidate(
    projection: ModuleType, public_repo: PublicRepo, change: str
) -> None:
    policy, receipt = _stage(projection, public_repo)
    forged = _changed_commit(
        public_repo, receipt["candidate_sha"], change, parent=public_repo.base
    )
    receipt.update(
        candidate_sha=forged,
        candidate_tree_sha=_git(public_repo.path, "rev-parse", f"{forged}^{{tree}}"),
        candidate_ref=f"refs/micro-eval-release/candidates/{forged}",
    )
    _git(public_repo.path, "update-ref", receipt["candidate_ref"], forged)
    public_repo.write_receipt(receipt)
    with pytest.raises(projection.ProjectionError, match="fixed source projection"):
        _verify(projection, public_repo, policy, forged)
    assert _git(public_repo.path, "rev-parse", "main") == public_repo.base


def test_publish_rechecks_source_projection_for_forged_verified_receipt(
    projection: ModuleType, public_repo: PublicRepo
) -> None:
    policy, staged = _stage(projection, public_repo)
    receipt = _verify(projection, public_repo, policy, staged["candidate_sha"])
    forged = _changed_commit(
        public_repo, receipt["candidate_sha"], "content", parent=public_repo.base
    )
    receipt.update(
        candidate_sha=forged,
        candidate_tree_sha=_git(public_repo.path, "rev-parse", f"{forged}^{{tree}}"),
        candidate_ref=f"refs/micro-eval-release/candidates/{forged}",
    )
    public_repo.write_receipt(receipt)
    _git(public_repo.path, "update-ref", "refs/heads/main", forged)
    with pytest.raises(projection.ProjectionError, match="fixed source projection"):
        projection.push_verified(
            public_repo.path, policy, "main", "origin", forged, dry_run=False
        )
    assert _git(public_repo.origin, "rev-parse", "main") == public_repo.base


@pytest.mark.parametrize("dispatch", ["remote-name", "symlink-name"])
def test_publish_preserves_original_pre_push_hook_dispatch(
    projection: ModuleType, public_repo: PublicRepo, dispatch: str
) -> None:
    policy, staged = _stage(projection, public_repo)
    candidate = staged["candidate_sha"]
    _verify(projection, public_repo, policy, candidate)
    hook = public_repo.path / ".git/hooks/pre-push"
    if dispatch == "remote-name":
        executable = hook
        condition = '[ "$1" = origin ]'
    else:
        executable = public_repo.path / ".git/shared-hook"
        hook.symlink_to("../shared-hook")
        condition = '[ "${0##*/}" = pre-push ]'
    executable.write_text(
        '#!/bin/sh\n'
        f'if {condition}; then\n'
        '  echo "original safety hook rejected publication" >&2\n'
        '  exit 1\n'
        'fi\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)

    with pytest.raises(projection.ProjectionError, match="original safety hook"):
        projection.push_verified(
            public_repo.path, policy, "main", "origin", candidate, dry_run=False
        )

    assert _git(public_repo.origin, "rev-parse", "main") == public_repo.base
    receipt = json.loads(public_repo.receipt_path(candidate).read_text(encoding="utf-8"))
    assert receipt["status"] == "verified"


@pytest.mark.parametrize("routing", ["second-url-rewrite", "remote-name-alias"])
def test_publish_rejects_redirected_target_after_url_resolution(
    projection: ModuleType, public_repo: PublicRepo, routing: str
) -> None:
    policy, staged = _stage(projection, public_repo)
    candidate = staged["candidate_sha"]
    _verify(projection, public_repo, policy, candidate)
    uninspected = public_repo.path.parent / "uninspected.git"
    uninspected.mkdir()
    _git(uninspected, "init", "--bare")
    _git(
        public_repo.path,
        "push",
        str(uninspected),
        f"{public_repo.base}:refs/heads/main",
    )
    _git(uninspected, "update-ref", "refs/heads/dev", public_repo.base)
    if routing == "second-url-rewrite":
        alias = "history-safety:approved-origin"
        _git(public_repo.path, "config", "remote.origin.url", alias)
        _git(
            public_repo.path,
            "config",
            f"url.{public_repo.origin}.pushInsteadOf",
            alias,
        )
        _git(
            public_repo.path,
            "config",
            f"url.{uninspected}.pushInsteadOf",
            str(public_repo.origin),
        )
        expected_url = str(public_repo.origin)
    else:
        _git(public_repo.path, "remote", "add", "secondary", str(public_repo.origin))
        _git(public_repo.path, "remote", "set-url", "--push", "secondary", str(uninspected))
        _git(public_repo.path, "config", "remote.origin.url", "secondary")
        expected_url = "secondary"
    assert _git(public_repo.path, "remote", "get-url", "--push", "origin") == expected_url

    with pytest.raises(projection.ProjectionError):
        projection.push_verified(
            public_repo.path, policy, "main", "origin", candidate, dry_run=False
        )

    assert _git(public_repo.origin, "rev-parse", "main") == public_repo.base
    assert _git(uninspected, "rev-parse", "main") == public_repo.base
    receipt = json.loads(public_repo.receipt_path(candidate).read_text(encoding="utf-8"))
    assert receipt["status"] == "verified"
