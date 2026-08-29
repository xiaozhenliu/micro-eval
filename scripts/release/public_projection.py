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

    @classmethod
    def load(cls, path: Path) -> "ProjectionPolicy":
        raw = path.read_bytes()
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
        )
        policy._validate()
        return policy

    def _validate(self) -> None:
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
    if not allow_glob and any(char in path for char in "*?["):
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
) -> subprocess.CompletedProcess[Any]:
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        check=False,
        text=text,
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


def project_public_tree(
    repo: Path,
    policy: ProjectionPolicy,
    source: str,
    target: str,
    version: str,
) -> dict[str, Any]:
    plan = policy.plan(repo, source)
    previous_target = _git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    already_projected = _git(
        repo,
        "merge-base",
        "--is-ancestor",
        plan.source_sha,
        previous_target,
        check=False,
    )
    if already_projected.returncode == 0:
        receipt = _read_receipt(repo, previous_target)
        if (
            receipt.get("status") == "verified"
            and receipt.get("candidate_sha") == previous_target
            and receipt.get("source_sha") == plan.source_sha
            and receipt.get("policy_sha256") == policy.digest
            and receipt.get("target_branch") == target
            and receipt.get("version") == version
        ):
            return receipt
        raise ProjectionError(
            "source is already in local target without a matching verified receipt"
        )
    generated = {item.target: item.source for item in policy.generated}
    candidate_sha = ""

    with tempfile.TemporaryDirectory(prefix="micro-eval-public-tree-") as temp_name:
        worktree = Path(temp_name)
        _git(repo, "worktree", "add", "--detach", str(worktree), previous_target)
        try:
            _git(worktree, "merge", "-s", "ours", "--no-commit", "--no-ff", plan.source_sha)
            merge_head = _git(worktree, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False)
            if merge_head.returncode != 0:
                raise ProjectionError("source is already projected; no merge commit was created")
            _git(worktree, "rm", "-r", "-q", "--ignore-unmatch", ".")
            _restore_paths(worktree, plan.source_sha, plan.public_paths)
            for target_path, source_path in generated.items():
                content = _run(
                    ("git", "-C", str(repo), "show", f"{plan.source_sha}:{source_path}"),
                    cwd=repo,
                    text=False,
                ).stdout
                destination = worktree / target_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            _git(worktree, "add", "-A")
            actual = tuple(
                item
                for item in _git(worktree, "ls-files", "-z").stdout.split("\0")
                if item
            )
            expected = plan.candidate_paths
            if tuple(sorted(actual)) != expected:
                unexpected = sorted(set(actual) - set(expected))
                missing = sorted(set(expected) - set(actual))
                raise ProjectionError(
                    f"candidate tree mismatch; unexpected={unexpected}, missing={missing}"
                )
            _scan_candidate(policy, worktree, expected)
            message = (
                f"release: project dev v{version} into main\n\n"
                f"Source: {plan.source_sha}\n"
                f"Policy: {plan.policy_sha256}\n"
                "Automated by the fail-closed public projection Module."
            )
            _git(worktree, "commit", "-m", message)
            candidate_sha = _git(worktree, "rev-parse", "HEAD").stdout.strip()
        finally:
            _git(repo, "worktree", "remove", "--force", str(worktree), check=False)

    if not candidate_sha:
        raise ProjectionError("candidate commit was not created")
    candidate_ref = f"refs/micro-eval-release/candidates/{candidate_sha}"
    _git(repo, "update-ref", candidate_ref, candidate_sha)
    receipt = {
        **plan.summary(),
        "candidate_sha": candidate_sha,
        "candidate_ref": candidate_ref,
        "previous_target_sha": previous_target,
        "source_branch": source,
        "target_branch": target,
        "version": version,
        "status": "staged",
    }
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
    resolved = _git(repo, "rev-parse", f"{candidate_sha}^{{commit}}").stdout.strip()
    if resolved != candidate_sha:
        raise ProjectionError("--candidate-sha must be a full commit SHA")
    receipt = _read_receipt(repo, candidate_sha)
    if receipt.get("candidate_sha") != candidate_sha:
        raise ProjectionError("release receipt does not match candidate")
    if receipt.get("status") not in {"staged", "verified"}:
        raise ProjectionError("release receipt is not staged for verification")
    if receipt.get("target_branch") != target:
        raise ProjectionError("release receipt target branch mismatch")
    if receipt.get("version") != version:
        raise ProjectionError("release receipt version mismatch")
    if receipt.get("policy_sha256") != policy.digest:
        raise ProjectionError("release receipt policy digest is stale")
    plan = policy.plan(repo, candidate_sha)
    expected = plan.candidate_paths
    actual = _git_paths(repo, candidate_sha)
    if actual != expected:
        raise ProjectionError("candidate tree does not match public policy")

    with tempfile.TemporaryDirectory(prefix="micro-eval-verify-tree-") as temp_name:
        worktree = Path(temp_name)
        _git(repo, "worktree", "add", "--detach", str(worktree), candidate_sha)
        try:
            _scan_candidate(policy, worktree, expected)
        finally:
            _git(repo, "worktree", "remove", "--force", str(worktree), check=False)

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
    verified = {**receipt, **artifacts, "status": "verified"}
    _write_json_atomic(_receipt_path(repo, candidate_sha), verified)
    candidate_ref = receipt.get("candidate_ref")
    if isinstance(candidate_ref, str) and candidate_ref:
        _git(repo, "update-ref", "-d", candidate_ref, candidate_sha, check=False)
    return verified


def _remote_has_branch(repo: Path, remote: str, branch: str) -> bool:
    result = _git(
        repo,
        "ls-remote",
        "--exit-code",
        "--heads",
        remote,
        f"refs/heads/{branch}",
        check=False,
    )
    if result.returncode == 0:
        return bool(result.stdout.strip())
    if result.returncode == 2:
        return False
    raise ProjectionError(
        f"could not inspect public remote {remote}: {result.stderr.strip()}"
    )


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


def push_verified(
    repo: Path,
    policy: ProjectionPolicy,
    target: str,
    remote: str,
    expected_sha: str,
    dry_run: bool,
    tag: str | None = None,
) -> dict[str, Any]:
    resolved = _git(repo, "rev-parse", f"{expected_sha}^{{commit}}").stdout.strip()
    if resolved != expected_sha:
        raise ProjectionError("--expected-sha must be a full commit SHA")
    local_target = _git(repo, "rev-parse", f"{target}^{{commit}}").stdout.strip()
    if local_target != expected_sha:
        raise ProjectionError(
            f"local {target} is {local_target}, not expected {expected_sha}"
        )
    receipt = _read_receipt(repo, expected_sha)
    if receipt.get("candidate_sha") != expected_sha:
        raise ProjectionError("release receipt does not match expected SHA")
    if receipt.get("status") != "verified":
        raise ProjectionError("release receipt is not verified")
    if receipt.get("policy_sha256") != policy.digest:
        raise ProjectionError("release receipt policy digest is stale")
    if receipt.get("target_branch") != target:
        raise ProjectionError("release receipt target branch mismatch")
    candidate_version = _git(repo, "show", f"{expected_sha}:VERSION").stdout.strip()
    if receipt.get("version") != candidate_version:
        raise ProjectionError("release receipt version does not match candidate")
    if _remote_has_branch(repo, remote, "dev"):
        raise ProjectionError(
            f"public remote {remote} contains forbidden branch refs/heads/dev"
        )
    _validate_release_tag(repo, receipt, expected_sha, tag, dry_run)
    print(f"Push target: {remote}/{target}", file=sys.stderr)
    print(f"Verified commit: {expected_sha}", file=sys.stderr)
    if tag is not None:
        print(f"Annotated tag: {tag} -> {expected_sha}", file=sys.stderr)
    if not dry_run:
        push_args = [
            "push",
            "--atomic",
            remote,
            f"{expected_sha}:refs/heads/{target}",
        ]
        if tag is not None:
            push_args.append(f"refs/tags/{tag}:refs/tags/{tag}")
        _git(repo, *push_args)
        receipt = {
            **receipt,
            "status": "published",
            "published_remote": remote,
            "published_tag": tag,
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
