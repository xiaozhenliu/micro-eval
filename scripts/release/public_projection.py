#!/usr/bin/env python3
"""Build and verify the deterministic public release projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


class ProjectionError(RuntimeError):
    """Raised when a public projection safety invariant fails."""


@dataclass(frozen=True)
class GeneratedPath:
    source: str
    target: str


@dataclass(frozen=True)
class ProjectionPlan:
    source_sha: str
    policy_sha256: str
    public_paths: tuple[str, ...]
    private_paths: tuple[str, ...]
    generated_paths: tuple[str, ...]

    @property
    def candidate_paths(self) -> tuple[str, ...]:
        return tuple(sorted((*self.public_paths, *self.generated_paths)))

    def summary(self) -> dict[str, Any]:
        return {
            "source_sha": self.source_sha,
            "policy_sha256": self.policy_sha256,
            "public_count": len(self.public_paths),
            "private_count": len(self.private_paths),
            "generated_count": len(self.generated_paths),
            "candidate_count": len(self.candidate_paths),
        }


@dataclass(frozen=True)
class ProjectionPolicy:
    path: Path
    public_patterns: tuple[str, ...]
    private_patterns: tuple[str, ...]
    required_public: tuple[str, ...]
    forbidden_public: tuple[str, ...]
    forbidden_content_markers: tuple[bytes, ...]
    content_scan_exclude: tuple[str, ...]
    generated: tuple[GeneratedPath, ...]
    sdist_patterns: tuple[str, ...]
    wheel_patterns: tuple[str, ...]
    digest: str
    history_base_sha: str | None = None
    document: str = ""

    @classmethod
    def load(cls, path: Path) -> "ProjectionPolicy":
        return cls.from_bytes(path, path.read_bytes())

    @classmethod
    def from_bytes(cls, path: Path, raw: bytes) -> "ProjectionPolicy":
        data = tomllib.loads(raw.decode("utf-8"))
        if data.get("version") != 1:
            raise ProjectionError("public projection policy version must be 1")
        paths = data.get("paths", {})
        artifacts = data.get("artifacts", {})
        generated = tuple(
            GeneratedPath(source=item["source"], target=item["target"])
            for item in data.get("generated", [])
        )
        policy = cls(
            path=path,
            public_patterns=tuple(paths.get("public", [])),
            private_patterns=tuple(paths.get("private", [])),
            required_public=tuple(paths.get("required_public", [])),
            forbidden_public=tuple(paths.get("forbidden_public", [])),
            forbidden_content_markers=tuple(
                marker.encode("utf-8")
                for marker in paths.get("forbidden_content_markers", [])
            ),
            content_scan_exclude=tuple(paths.get("content_scan_exclude", [])),
            generated=generated,
            sdist_patterns=tuple(artifacts.get("sdist", [])),
            wheel_patterns=tuple(artifacts.get("wheel", [])),
            digest=hashlib.sha256(raw).hexdigest(),
            history_base_sha=data.get("history", {}).get("public_base_sha"),
            document=raw.decode("utf-8"),
        )
        policy._validate()
        return policy

    def _validate(self) -> None:
        if self.history_base_sha is not None and not re.fullmatch(
            r"[0-9a-f]{40}", self.history_base_sha
        ):
            raise ProjectionError("history public_base_sha must be a full commit SHA")
        if not self.public_patterns or not self.private_patterns:
            raise ProjectionError("policy must define public and private paths")
        targets = [item.target for item in self.generated]
        if len(targets) != len(set(targets)):
            raise ProjectionError("generated targets must be unique")
        for value in (
            *self.public_patterns,
            *self.private_patterns,
            *self.required_public,
            *self.forbidden_public,
            *self.content_scan_exclude,
            *(item.source for item in self.generated),
            *(item.target for item in self.generated),
        ):
            _validate_repo_path(value, allow_glob=True)

    def plan(self, repo: Path, source: str) -> ProjectionPlan:
        if source == "WORKTREE":
            source_sha = _git(repo, "rev-parse", "HEAD^{commit}").stdout.strip()
            tracked = _worktree_paths(repo)
        else:
            source_sha = _git(repo, "rev-parse", f"{source}^{{commit}}").stdout.strip()
            tracked = _git_paths(repo, source_sha)
        generated_targets = {item.target for item in self.generated}
        public: list[str] = []
        private: list[str] = []
        generated: list[str] = []
        errors: list[str] = []

        for path in tracked:
            categories: list[str] = []
            if path in generated_targets:
                categories.append("generated")
            if _matches_any(path, self.public_patterns):
                categories.append("public")
            if _matches_any(path, self.private_patterns):
                categories.append("private")
            if len(categories) != 1:
                label = "unclassified" if not categories else "/".join(categories)
                errors.append(f"{path}: {label}")
                continue
            category = categories[0]
            if category == "public":
                public.append(path)
            elif category == "private":
                private.append(path)
            else:
                generated.append(path)

        tracked_set = set(tracked)
        missing = [
            path
            for path in self.required_public
            if path not in tracked_set and path not in generated_targets
        ]
        if missing:
            errors.extend(f"{path}: required public path is missing" for path in missing)

        candidate = (*public, *generated)
        forbidden = [
            path for path in candidate if _matches_any(path, self.forbidden_public)
        ]
        if forbidden:
            errors.extend(f"{path}: forbidden public path" for path in forbidden)
        if errors:
            detail = "\n  ".join(errors[:40])
            suffix = "" if len(errors) <= 40 else f"\n  ... {len(errors) - 40} more"
            raise ProjectionError(f"public path classification failed:\n  {detail}{suffix}")

        return ProjectionPlan(
            source_sha=source_sha,
            policy_sha256=self.digest,
            public_paths=tuple(sorted(public)),
            private_paths=tuple(sorted(private)),
            generated_paths=tuple(sorted(generated_targets)),
        )


def _validate_repo_path(path: str, *, allow_glob: bool = False) -> None:
    if not path or path.startswith("/"):
        raise ProjectionError(f"path must be non-empty and repository-relative: {path!r}")
    parts = PurePosixPath(path).parts
    if ".." in parts or "." in parts:
        raise ProjectionError(f"path traversal is not allowed: {path!r}")
    if not allow_glob and any(char in path for char in "*?"):
        raise ProjectionError(f"unexpected glob in concrete path: {path!r}")


def _compile_glob(pattern: str) -> re.Pattern[str]:
    result: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                result.append(".*")
                index += 2
            else:
                result.append("[^/]*")
                index += 1
        elif char == "?":
            result.append("[^/]")
            index += 1
        else:
            result.append(re.escape(char))
            index += 1
    result.append("$")
    return re.compile("".join(result))


def _matches(path: str, pattern: str) -> bool:
    return bool(_compile_glob(pattern).fullmatch(path))


def _matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(_matches(path, pattern) for pattern in patterns)


def _run(
    argv: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    text: bool = True,
    input: bytes | None = None,
) -> subprocess.CompletedProcess[Any]:
    if argv[0] == "git":
        argv = ("git", "--no-replace-objects", *argv[1:])
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        check=False,
        text=text,
        input=input,
    )
    if check and result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode("utf-8", "replace")
        raise ProjectionError(f"command failed: {argv!r}\n{stderr.strip()}")
    return result


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(("git", "-C", str(repo), *args), cwd=repo, check=check)


def _git_paths(repo: Path, ref: str) -> tuple[str, ...]:
    result = _run(
        ("git", "-C", str(repo), "ls-tree", "-r", "-z", "--name-only", ref),
        cwd=repo,
        text=False,
    )
    return tuple(
        sorted(
            item.decode("utf-8")
            for item in result.stdout.split(b"\0")
            if item
        )
    )


def _worktree_paths(repo: Path) -> tuple[str, ...]:
    tracked_result = _run(
        ("git", "-C", str(repo), "ls-files", "-z"),
        cwd=repo,
        text=False,
    )
    untracked_result = _run(
        (
            "git",
            "-C",
            str(repo),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ),
        cwd=repo,
        text=False,
    )
    paths = {
        item.decode("utf-8")
        for item in (*tracked_result.stdout.split(b"\0"), *untracked_result.stdout.split(b"\0"))
        if item
    }
    return tuple(
        sorted(
            path
            for path in paths
            if (repo / path).exists() or (repo / path).is_symlink()
        )
    )


def _repo_root() -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd())
    return Path(result.stdout.strip()).resolve()


def _receipt_dir(repo: Path) -> Path:
    common = _git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = repo / common_path
    return common_path.resolve() / "micro-eval-release" / "receipts"


def _receipt_path(repo: Path, sha: str) -> Path:
    return _receipt_dir(repo) / f"{sha}.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _read_receipt(repo: Path, sha: str) -> dict[str, Any]:
    path = _receipt_path(repo, sha)
    if not path.is_file():
        raise ProjectionError(f"verified release receipt not found for {sha}")
    return json.loads(path.read_text(encoding="utf-8"))


def _restore_paths(worktree: Path, source_sha: str, paths: Sequence[str]) -> None:
    for start in range(0, len(paths), 100):
        chunk = paths[start : start + 100]
        _git(worktree, "checkout", source_sha, "--", *chunk)


def _scan_candidate(policy: ProjectionPolicy, root: Path, paths: Iterable[str]) -> None:
    for relative in paths:
        _validate_repo_path(relative)
        path = root / relative
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or ".." in PurePosixPath(target).parts:
                raise ProjectionError(f"unsafe public symlink: {relative} -> {target}")
            continue
        if not path.is_file():
            raise ProjectionError(f"candidate path is not a regular file: {relative}")
        if _matches_any(relative, policy.content_scan_exclude):
            continue
        if not policy.forbidden_content_markers:
            continue
        with path.open("rb") as handle:
            content = handle.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            continue
        for marker in policy.forbidden_content_markers:
            if marker in content:
                raise ProjectionError(f"forbidden private-key marker in {relative}")


def _require_history_proof(repo: Path, policy: ProjectionPolicy) -> str:
    base = policy.history_base_sha
    if base is None:
        raise ProjectionError("explicit history public_base_sha is required; migrate the policy")
    for name in (
        "GIT_REPLACE_REF_BASE", "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE", "GIT_DIR",
        "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_NAMESPACE", "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_INDEX_FILE",
    ):
        if name in os.environ:
            raise ProjectionError(f"history proof forbids ambient {name}")
    if _git(repo, "rev-parse", "--is-shallow-repository").stdout.strip() != "false":
        raise ProjectionError("history proof forbids a shallow repository")
    if _git(repo, "for-each-ref", "--format=%(refname)", "refs/replace/").stdout.strip():
        raise ProjectionError("history proof forbids replace refs")
    graft_path = Path(_git(repo, "rev-parse", "--git-path", "info/grafts").stdout.strip())
    if not graft_path.is_absolute():
        graft_path = repo / graft_path
    if graft_path.exists():
        raise ProjectionError("history proof forbids grafts")
    if _git(repo, "rev-parse", "--verify", f"{base}^{{commit}}").stdout.strip() != base:
        raise ProjectionError("public history base must identify a commit")
    return base


def _tree_entries(repo: Path, ref: str) -> dict[str, tuple[str, str, str]]:
    raw = _run(
        ("git", "-C", str(repo), "ls-tree", "-r", "-z", ref), cwd=repo, text=False
    ).stdout
    entries = {}
    for record in raw.split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
            entries[path.decode("utf-8")] = (mode, kind, oid)
    return entries


def _scan_public_tree(
    repo: Path, policy: ProjectionPolicy, ref: str,
    entries: dict[str, tuple[str, str, str]],
) -> None:
    generated = {item.target for item in policy.generated}
    scan: list[tuple[str, str, str]] = []
    for path, (mode, kind, oid) in entries.items():
        _validate_repo_path(path)
        public = _matches_any(path, policy.public_patterns)
        private = _matches_any(path, policy.private_patterns)
        if private or int(public) + int(path in generated) != 1:
            raise ProjectionError(f"non-public path in history {ref}: {path}")
        if _matches_any(path, policy.forbidden_public):
            raise ProjectionError(f"forbidden public path in history {ref}: {path}")
        if kind != "blob" or mode not in {"100644", "100755", "120000"}:
            raise ProjectionError(f"unsupported public tree entry: {path} ({mode} {kind})")
        if mode == "120000" or (
            policy.forbidden_content_markers
            and not _matches_any(path, policy.content_scan_exclude)
        ):
            scan.append((path, mode, oid))
    if not scan:
        return
    raw = _run(
        ("git", "-C", str(repo), "cat-file", "--batch"), cwd=repo, text=False,
        input="".join(f"{oid}\n" for _, _, oid in scan).encode("ascii"),
    ).stdout
    offset = 0
    for path, mode, oid in scan:
        end = raw.index(b"\n", offset)
        actual_oid, kind, size = raw[offset:end].split()
        if actual_oid.decode() != oid or kind != b"blob":
            raise ProjectionError(f"invalid public blob: {path}")
        offset = end + 1
        content = raw[offset:offset + int(size)]
        offset += int(size) + 1
        if mode == "120000":
            link = content.decode("utf-8")
            if os.path.isabs(link) or ".." in PurePosixPath(link).parts:
                raise ProjectionError(f"unsafe public symlink: {path}")
        elif any(marker in content for marker in policy.forbidden_content_markers):
            raise ProjectionError(f"forbidden private-key marker in {path}")


def verify_public_history(
    repo: Path, policy: ProjectionPolicy, candidate_sha: str,
    *, expected_parent: str | None = None,
) -> None:
    """Prove the actual object graph after the explicitly approved public base."""
    base = _require_history_proof(repo, policy)
    candidate = _git(repo, "rev-parse", "--verify", f"{candidate_sha}^{{commit}}").stdout.strip()
    if _git(repo, "merge-base", "--is-ancestor", base, candidate, check=False).returncode:
        raise ProjectionError("candidate does not descend from the approved public history base")
    if expected_parent is not None:
        parents = _git(repo, "show", "-s", "--format=%P", candidate).stdout.split()
        if parents != [expected_parent]:
            raise ProjectionError("candidate must have exactly the expected single parent")
    history = _git(repo, "rev-list", "--reverse", "--parents", f"{base}..{candidate}").stdout
    previous = base
    for line in history.splitlines():
        commit, *parents = line.split()
        if parents != [previous]:
            raise ProjectionError(f"public history must be a single-parent chain: {commit}")
        _scan_public_tree(repo, policy, commit, _tree_entries(repo, commit))
        previous = commit


def _expected_source_entries(
    repo: Path, policy: ProjectionPolicy, source_sha: str,
) -> tuple[ProjectionPlan, dict[str, tuple[str, str, str]]]:
    plan = policy.plan(repo, source_sha)
    source_entries = _tree_entries(repo, source_sha)
    expected = {path: source_entries[path] for path in plan.public_paths}
    for item in policy.generated:
        entry = source_entries.get(item.source)
        if entry is None or entry[1] != "blob" or entry[0] not in {"100644", "100755"}:
            raise ProjectionError(f"generated template must be a regular source blob: {item.source}")
        expected[item.target] = ("100644", "blob", entry[2])
    for path in expected:
        if any(str(parent) in expected for parent in PurePosixPath(path).parents):
            raise ProjectionError(f"projected path has a file/symlink ancestor: {path}")
    return plan, expected


def _validate_receipt(
    repo: Path, policy: ProjectionPolicy, receipt: dict[str, Any],
    candidate_sha: str, target: str, version: str,
) -> None:
    if receipt.get("receipt_version") != 2 or receipt.get("projection_mode") != "single-parent":
        raise ProjectionError("legacy release receipt rejected; migrate through the approved history cleanup")
    if receipt.get("candidate_sha") != candidate_sha:
        raise ProjectionError("release receipt does not match candidate")
    if receipt.get("status") not in {"staged", "verified", "published"}:
        raise ProjectionError("invalid release receipt status")
    if receipt.get("target_branch") != target or receipt.get("source_branch") != "dev":
        raise ProjectionError("release receipt branch mismatch")
    if receipt.get("version") != version:
        raise ProjectionError("release receipt version mismatch")
    if receipt.get("policy_sha256") != policy.digest:
        raise ProjectionError("release receipt policy digest is stale")
    if receipt.get("policy_document") != policy.document:
        raise ProjectionError("release receipt policy snapshot mismatch")
    if receipt.get("history_base_sha") != policy.history_base_sha:
        raise ProjectionError("release receipt history base mismatch")
    for key in ("source_sha", "previous_target_sha", "publication_base_sha", "candidate_tree_sha"):
        if not isinstance(receipt.get(key), str) or not re.fullmatch(r"[0-9a-f]{40}", receipt[key]):
            raise ProjectionError(f"invalid release receipt {key}")
    if receipt.get("candidate_ref") != f"refs/micro-eval-release/candidates/{candidate_sha}":
        raise ProjectionError("release receipt candidate ref mismatch")
    message = _git(repo, "show", "-s", "--format=%B", candidate_sha).stdout
    if (
        message.splitlines().count(f"Source: {receipt['source_sha']}") != 1
        or message.splitlines().count(f"Policy: {policy.digest}") != 1
        or message.splitlines().count(f"Public-Base: {policy.history_base_sha}") != 1
        or message.splitlines().count(f"Publication-Base: {receipt['publication_base_sha']}") != 1
    ):
        raise ProjectionError("release receipt source/policy does not match commit metadata")
    verify_public_history(repo, policy, candidate_sha, expected_parent=receipt["previous_target_sha"])
    if _git(repo, "merge-base", "--is-ancestor", receipt["publication_base_sha"], receipt["previous_target_sha"], check=False).returncode:
        raise ProjectionError("publication base is not an ancestor of the previous public target")
    if _git(repo, "merge-base", "--is-ancestor", str(policy.history_base_sha), receipt["publication_base_sha"], check=False).returncode:
        raise ProjectionError("publication base predates the approved public history base")
    plan, expected = _expected_source_entries(repo, policy, receipt["source_sha"])
    if any(receipt.get(key) != value for key, value in plan.summary().items()):
        raise ProjectionError("release receipt source projection summary mismatch")
    if _tree_entries(repo, candidate_sha) != expected:
        raise ProjectionError("candidate tree does not match the fixed source projection (paths/content/modes/templates)")
    tree = _git(repo, "rev-parse", f"{candidate_sha}^{{tree}}").stdout.strip()
    if receipt["candidate_tree_sha"] != tree:
        raise ProjectionError("release receipt candidate tree mismatch")
    for ref in (candidate_sha, receipt["source_sha"]):
        if _git(repo, "show", f"{ref}:VERSION").stdout.strip() != version:
            raise ProjectionError("release receipt version does not match candidate/source")


def project_public_tree(
    repo: Path,
    policy: ProjectionPolicy,
    source: str,
    target: str,
    version: str,
) -> dict[str, Any]:
    if source != "dev" or target != "main":
        raise ProjectionError("projection requires source dev and target main")
    _require_history_proof(repo, policy)
    plan, expected_entries = _expected_source_entries(repo, policy, source)
    previous_target = _git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    verify_public_history(repo, policy, previous_target)
    if _git(repo, "show", f"{plan.source_sha}:VERSION").stdout.strip() != version:
        raise ProjectionError("source version does not match requested release")
    _scan_public_tree(repo, policy, plan.source_sha, expected_entries)

    # A verified/published target or a staged candidate is reusable only after
    # proving its complete receipt, source projection, and actual parent graph.
    paths = [_receipt_path(repo, previous_target)]
    paths.extend(sorted(_receipt_dir(repo).glob("*.json")))
    for path in dict.fromkeys(paths):
        if not path.is_file():
            continue
        receipt = json.loads(path.read_text(encoding="utf-8"))
        is_current = receipt.get("candidate_sha") == previous_target
        if is_current and (receipt.get("receipt_version") != 2 or receipt.get("projection_mode") != "single-parent"):
            raise ProjectionError("legacy release receipt rejected; migrate through the approved history cleanup")
        if (
            receipt.get("source_sha") == plan.source_sha
            and receipt.get("policy_sha256") == policy.digest
            and receipt.get("target_branch") == target
            and receipt.get("version") == version
            and (is_current or (
                receipt.get("status") == "staged"
                and receipt.get("previous_target_sha") == previous_target
            ))
        ):
            _validate_receipt(repo, policy, receipt, receipt["candidate_sha"], target, version)
            return receipt

    publication_base = previous_target
    previous_path = _receipt_path(repo, previous_target)
    if previous_path.is_file():
        previous_receipt = _read_receipt(repo, previous_target)
        document = previous_receipt.get("policy_document")
        if not isinstance(document, str):
            raise ProjectionError("previous release receipt has no policy snapshot; explicit migration is required")
        previous_policy = ProjectionPolicy.from_bytes(policy.path, document.encode("utf-8"))
        if previous_policy.history_base_sha != policy.history_base_sha:
            raise ProjectionError("normal staging cannot change the approved public history base")
        _validate_receipt(repo, previous_policy, previous_receipt, previous_target, target, previous_receipt.get("version", ""))
        if previous_receipt["status"] != "published":
            publication_base = previous_receipt["publication_base_sha"]

    with tempfile.TemporaryDirectory(prefix="micro-eval-public-tree-") as temp_name:
        worktree = Path(temp_name)
        _git(repo, "worktree", "add", "--detach", str(worktree), previous_target)
        try:
            _git(worktree, "rm", "-r", "-q", "--ignore-unmatch", ".")
            _restore_paths(worktree, plan.source_sha, plan.public_paths)
            for item in policy.generated:
                content = _run(
                    ("git", "-C", str(repo), "cat-file", "blob", expected_entries[item.target][2]),
                    cwd=repo, text=False,
                ).stdout
                destination = worktree / item.target
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(0o644)
            _git(worktree, "add", "-A")
            tree = _git(worktree, "write-tree").stdout.strip()
            if _tree_entries(repo, tree) != expected_entries:
                raise ProjectionError("candidate tree does not match the fixed source projection")
            _scan_public_tree(repo, policy, tree, expected_entries)
            message = (
                f"release: project dev v{version} into main\n\n"
                f"Source: {plan.source_sha}\n"
                f"Policy: {plan.policy_sha256}\n"
                f"Public-Base: {policy.history_base_sha}\n"
                f"Publication-Base: {publication_base}\n"
                "Automated by the fail-closed public projection Module."
            )
            # commit-tree makes the only parent explicit. dev is metadata only.
            candidate_sha = _git(repo, "commit-tree", tree, "-p", previous_target, "-m", message).stdout.strip()
        finally:
            _git(repo, "worktree", "remove", "--force", str(worktree), check=False)

    candidate_ref = f"refs/micro-eval-release/candidates/{candidate_sha}"
    receipt = {
        **plan.summary(),
        "receipt_version": 2,
        "policy_document": policy.document,
        "projection_mode": "single-parent",
        "candidate_sha": candidate_sha,
        "candidate_tree_sha": tree,
        "candidate_ref": candidate_ref,
        "previous_target_sha": previous_target,
        "history_base_sha": policy.history_base_sha,
        "publication_base_sha": publication_base,
        "source_branch": source,
        "target_branch": target,
        "version": version,
        "status": "staged",
    }
    _validate_receipt(repo, policy, receipt, candidate_sha, target, version)
    _git(repo, "update-ref", candidate_ref, candidate_sha)
    _write_json_atomic(_receipt_path(repo, candidate_sha), receipt)
    return receipt


def _safe_archive_path(name: str) -> str:
    normalized = name.rstrip("/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or "\\" in normalized
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ProjectionError(f"unsafe archive path: {name!r}")
    return normalized


def _verify_archive_entries(
    entries: Iterable[str], patterns: Sequence[str], label: str
) -> tuple[str, ...]:
    normalized = tuple(sorted(_safe_archive_path(entry) for entry in entries))
    unknown = [entry for entry in normalized if not _matches_any(entry, patterns)]
    if unknown:
        raise ProjectionError(f"unexpected {label} entries: {unknown[:30]}")
    return normalized


def verify_artifacts(
    policy: ProjectionPolicy, dist_dir: Path, version: str
) -> dict[str, Any]:
    sdist = dist_dir / f"micro_eval-{version}.tar.gz"
    wheel = dist_dir / f"micro_eval-{version}-py3-none-any.whl"
    if not sdist.is_file() or not wheel.is_file():
        raise ProjectionError(f"release artifacts missing for version {version}")

    prefix = f"micro_eval-{version}/"
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_entries: list[str] = []
        for member in archive.getmembers():
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                raise ProjectionError(f"links are forbidden in sdist: {member.name}")
            name = _safe_archive_path(member.name)
            if not name.startswith(prefix):
                raise ProjectionError(f"sdist entry is outside package root: {name}")
            sdist_entries.append(name[len(prefix) :])
    checked_sdist = _verify_archive_entries(
        sdist_entries, policy.sdist_patterns, "sdist"
    )

    with zipfile.ZipFile(wheel) as archive:
        wheel_entries: list[str] = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ProjectionError(f"links are forbidden in wheel: {info.filename}")
            wheel_entries.append(info.filename)
    checked_wheel = _verify_archive_entries(
        wheel_entries, policy.wheel_patterns, "wheel"
    )
    return {
        "sdist": sdist.name,
        "sdist_sha256": _sha256_file(sdist),
        "sdist_entry_count": len(checked_sdist),
        "wheel": wheel.name,
        "wheel_sha256": _sha256_file(wheel),
        "wheel_entry_count": len(checked_wheel),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_projection(
    repo: Path,
    policy: ProjectionPolicy,
    candidate_sha: str,
    target: str,
    dist_dir: Path,
    version: str,
) -> dict[str, Any]:
    _require_history_proof(repo, policy)
    resolved = _git(repo, "rev-parse", f"{candidate_sha}^{{commit}}").stdout.strip()
    if resolved != candidate_sha:
        raise ProjectionError("--candidate-sha must be a full commit SHA")
    receipt = _read_receipt(repo, candidate_sha)
    _validate_receipt(repo, policy, receipt, candidate_sha, target, version)

    artifacts = verify_artifacts(policy, dist_dir, version)
    previous_target = str(receipt.get("previous_target_sha", ""))
    local_target = _git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    if local_target == previous_target:
        _git(
            repo,
            "update-ref",
            f"refs/heads/{target}",
            candidate_sha,
            previous_target,
        )
    elif local_target != candidate_sha:
        raise ProjectionError(
            f"local {target} changed during verification: {local_target}"
        )
    verified = {**receipt, **artifacts, "status": "published" if receipt["status"] == "published" else "verified"}
    _write_json_atomic(_receipt_path(repo, candidate_sha), verified)
    candidate_ref = receipt.get("candidate_ref")
    if isinstance(candidate_ref, str) and candidate_ref:
        _git(repo, "update-ref", "-d", candidate_ref, candidate_sha, check=False)
    return verified


def _validate_release_tag(
    repo: Path,
    receipt: dict[str, Any],
    expected_sha: str,
    tag: str | None,
    dry_run: bool,
) -> None:
    if tag is None:
        return
    expected_tag = f"v{receipt.get('version', '')}"
    if tag != expected_tag:
        raise ProjectionError(f"release tag must be exactly {expected_tag}")
    ref = f"refs/tags/{tag}"
    if _git(repo, "check-ref-format", ref, check=False).returncode != 0:
        raise ProjectionError(f"invalid release tag: {tag}")
    existing = _git(repo, "rev-parse", "-q", "--verify", ref, check=False)
    if existing.returncode == 0:
        kind = _git(repo, "cat-file", "-t", ref).stdout.strip()
        target = _git(repo, "rev-parse", f"{ref}^{{commit}}").stdout.strip()
        if kind != "tag" or target != expected_sha:
            raise ProjectionError(
                f"existing tag {tag} is not an annotated tag for {expected_sha}"
            )
    elif not dry_run:
        _git(repo, "tag", "-a", tag, expected_sha, "-m", f"Release {tag}")


def _remote_snapshot(repo: Path, url: str, target: str, tag: str | None) -> dict[str, str]:
    patterns = [f"refs/heads/{target}", "refs/heads/dev", "refs/heads/agent/*", "refs/heads/human/*"]
    if tag:
        patterns.append(f"refs/tags/{tag}")
    output = _git(repo, "ls-remote", "--refs", url, *patterns).stdout
    refs = dict(line.split()[::-1] for line in output.splitlines())
    for ref in refs:
        if ref == "refs/heads/dev" or ref.startswith(("refs/heads/agent/", "refs/heads/human/")):
            raise ProjectionError(f"public remote contains forbidden branch {ref}")
    return refs


def _guarded_push(
    repo: Path, remote: str, url: str, updates: dict[str, tuple[str, str]],
) -> None:
    # The hook receives the receive-pack advertisement used by this exact push,
    # closing the ls-remote -> push rollback window without permitting force.
    hook = Path(_git(repo, "rev-parse", "--git-path", "hooks/pre-push").stdout.strip())
    if not hook.is_absolute():
        hook = repo / hook
    existing_hook = str(hook.absolute()) if hook.is_file() and os.access(hook, os.X_OK) else None
    with tempfile.TemporaryDirectory(prefix="micro-eval-push-guard-") as temp_name:
        hooks = Path(temp_name)
        guard = hooks / "pre-push"
        guard.write_text(
            f"#!{sys.executable}\n"
            "import json, subprocess, sys\n"
            f"expected = json.loads({json.dumps(json.dumps(updates))})\n"
            f"existing = {existing_hook!r}\n"
            f"original_args = {[remote, url]!r}\n"
            "if len(sys.argv) != 3 or sys.argv[2] != original_args[1]:\n"
            "    sys.exit('release pre-push guard: publication destination changed')\n"
            "data = sys.stdin.buffer.read()\n"
            "seen = set()\n"
            "for line in data.decode().splitlines():\n"
            "    local_ref, local_oid, remote_ref, remote_oid = line.split()\n"
            "    if remote_ref in seen or expected.get(remote_ref) != [local_oid, remote_oid]:\n"
            "        sys.exit('release pre-push guard: remote advertisement/refspec changed')\n"
            "    seen.add(remote_ref)\n"
            "for ref, (new, old) in expected.items():\n"
            "    if new != old and ref not in seen:\n"
            "        sys.exit('release pre-push guard: expected update missing')\n"
            "if existing:\n"
            "    sys.exit(subprocess.run([existing, *original_args], input=data).returncode)\n",
            encoding="utf-8",
        )
        guard.chmod(0o700)
        args = [
            "-c", f"core.hooksPath={hooks}",
            "-c", "push.followTags=false",
            "-c", "push.default=nothing",
            "-c", f"remote.{remote}.mirror=false",
            "-c", "push.useForceIfIncludes=false",
            "push", "--atomic", "--no-force", "--no-follow-tags",
            "--recurse-submodules=no", url,
        ]
        args.extend(f"{new}:{ref}" for ref, (new, _) in updates.items())
        _git(repo, *args)


def push_verified(
    repo: Path,
    policy: ProjectionPolicy,
    target: str,
    remote: str,
    expected_sha: str,
    dry_run: bool,
    tag: str | None = None,
) -> dict[str, Any]:
    _require_history_proof(repo, policy)
    if target != "main" or remote != "origin":
        raise ProjectionError("publication is restricted to origin/main")
    resolved = _git(repo, "rev-parse", f"{expected_sha}^{{commit}}").stdout.strip()
    if resolved != expected_sha:
        raise ProjectionError("--expected-sha must be a full commit SHA")
    local_target = _git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    if local_target != expected_sha:
        raise ProjectionError(f"local {target} is {local_target}, not expected {expected_sha}")
    receipt = _read_receipt(repo, expected_sha)
    _validate_receipt(repo, policy, receipt, expected_sha, target, receipt.get("version", ""))
    if receipt["status"] not in {"verified", "published"}:
        raise ProjectionError("release receipt is not verified")
    if receipt["status"] == "published" and receipt.get("published_remote") != remote:
        raise ProjectionError("published receipt remote mismatch")
    urls = _git(repo, "remote", "get-url", "--push", "--all", remote).stdout.splitlines()
    if len(urls) != 1:
        raise ProjectionError("publication requires exactly one push URL")
    url = urls[0]
    rewrites = _git(
        repo, "config", "--null", "--get-regexp",
        r"^url\..*\.(insteadof|pushinsteadof)$", check=False,
    )
    if rewrites.returncode not in {0, 1}:
        raise ProjectionError("could not inspect publication URL rewriting")
    for record in rewrites.stdout.split("\0"):
        if record and url.startswith(record.split("\n", 1)[1]):
            raise ProjectionError("resolved publication URL is subject to further Git URL rewriting")
    refs = _remote_snapshot(repo, url, target, tag)
    target_ref = f"refs/heads/{target}"
    remote_tip = refs.get(target_ref)
    if remote_tip is None:
        raise ProjectionError("public remote main is missing; explicit history initialization is required")
    expected_remote = expected_sha if receipt["status"] == "published" else receipt["publication_base_sha"]
    if remote_tip not in {expected_remote, expected_sha}:
        raise ProjectionError("public remote main advanced, diverged, or rolled back from the verified publication base")
    # Both accepted OIDs are local verified history, so never fetch an unknown tip.
    verify_public_history(repo, policy, remote_tip)
    _validate_release_tag(repo, receipt, expected_sha, tag, dry_run)
    updates = {target_ref: (expected_sha, remote_tip)}
    if tag is not None:
        tag_ref = f"refs/tags/{tag}"
        local_tag = _git(repo, "rev-parse", "-q", "--verify", tag_ref, check=False)
        if local_tag.returncode == 0:
            tag_oid = local_tag.stdout.strip()
            remote_tag = refs.get(tag_ref, "0" * 40)
            if remote_tag not in {"0" * 40, tag_oid}:
                raise ProjectionError("remote release tag differs from the approved local annotated tag")
            updates[tag_ref] = (tag_oid, remote_tag)
        elif refs.get(tag_ref):
            raise ProjectionError("remote release tag exists without the approved local annotated tag")
    print(f"Push target: {remote}/{target}", file=sys.stderr)
    print(f"Verified commit: {expected_sha}", file=sys.stderr)
    if tag is not None:
        print(f"Annotated tag: {tag} -> {expected_sha}", file=sys.stderr)
    if not dry_run:
        _guarded_push(repo, remote, url, updates)
        receipt = {
            **receipt,
            "status": "published",
            "published_remote": remote,
            "published_tag": tag if tag is not None else receipt.get("published_tag"),
        }
        _write_json_atomic(_receipt_path(repo, expected_sha), receipt)
    return receipt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("scripts/release/public-projection.toml"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--source", default="HEAD")
    plan_parser.add_argument("--json", action="store_true")

    project_parser = subparsers.add_parser("project")
    project_parser.add_argument("--source", default="dev")
    project_parser.add_argument("--target", default="main")
    project_parser.add_argument("--version", required=True)
    project_parser.add_argument("--json", action="store_true")

    history_parser = subparsers.add_parser("verify-history")
    history_parser.add_argument("--candidate-sha", required=True)
    history_parser.add_argument("--json", action="store_true")

    artifacts_parser = subparsers.add_parser("verify-artifacts")
    artifacts_parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    artifacts_parser.add_argument("--version", required=True)
    artifacts_parser.add_argument("--json", action="store_true")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--candidate-sha", required=True)
    verify_parser.add_argument("--target", default="main")
    verify_parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    verify_parser.add_argument("--version", required=True)
    verify_parser.add_argument("--json", action="store_true")

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("--target", default="main")
    push_parser.add_argument("--remote", default="origin")
    push_parser.add_argument("--expected-sha", required=True)
    push_parser.add_argument("--tag")
    push_parser.add_argument("--dry-run", action="store_true")
    push_parser.add_argument("--json", action="store_true")
    return parser


def _print_result(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, sort_keys=True))
    else:
        for key, item in value.items():
            print(f"{key}: {item}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        repo = _repo_root()
        policy_path = args.policy
        if not policy_path.is_absolute():
            policy_path = repo / policy_path
        policy = ProjectionPolicy.load(policy_path)
        if args.command == "plan":
            result = policy.plan(repo, args.source).summary()
        elif args.command == "project":
            result = project_public_tree(
                repo, policy, args.source, args.target, args.version
            )
        elif args.command == "verify-history":
            verify_public_history(repo, policy, args.candidate_sha)
            result = {
                "candidate_sha": _git(repo, "rev-parse", f"{args.candidate_sha}^{{commit}}").stdout.strip(),
                "history_base_sha": policy.history_base_sha,
            }
        elif args.command == "verify-artifacts":
            dist_dir = args.dist_dir if args.dist_dir.is_absolute() else repo / args.dist_dir
            result = verify_artifacts(policy, dist_dir, args.version)
        elif args.command == "verify":
            dist_dir = args.dist_dir if args.dist_dir.is_absolute() else repo / args.dist_dir
            result = verify_projection(
                repo,
                policy,
                args.candidate_sha,
                args.target,
                dist_dir,
                args.version,
            )
        elif args.command == "push":
            result = push_verified(
                repo,
                policy,
                args.target,
                args.remote,
                args.expected_sha,
                args.dry_run,
                args.tag,
            )
        else:  # pragma: no cover
            raise ProjectionError(f"unknown command: {args.command}")
        _print_result(result, args.json)
        return 0
    except (OSError, ProjectionError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
