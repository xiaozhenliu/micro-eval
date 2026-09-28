from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parents[2]
RELEASE_SCRIPT = PROJECT_ROOT / "scripts" / "release-to-main.sh"
PREFLIGHT_SCRIPT = PROJECT_ROOT / "scripts" / "release" / "preflight-release.sh"
PROJECTION_FILES = (
    "scripts/release/public_projection.py",
    "scripts/release/public-projection.toml",
    "scripts/release/main.gitignore",
)
AGENTS_TEMPLATE = (
    ".codex/skills/micro-eval-release/assets/templates/agents-publish-template.md"
)
PUBLIC_AGENTS = "AGENTS.md"
VERSION = "1.2.3"


@dataclass(frozen=True)
class ReleaseRepo:
    worktree: Path
    origin: Path
    env: dict[str, str]


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        pytest.fail(
            f"command failed ({result.returncode}): {argv!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", "-C", str(repo), *args], cwd=repo, check=check)


def _bare_git(origin: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(
        ["git", f"--git-dir={origin}", *args], cwd=origin.parent, check=check
    )


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _write_project_file(repo: Path, relative_path: str, content: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_project_file(repo: Path, relative_path: str) -> None:
    destination = repo / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / relative_path, destination)


def _fake_uv_script() -> str:
    return f'''#!/usr/bin/env python3
import io
import pathlib
import subprocess
import sys
import tarfile
import zipfile

args = sys.argv[1:]
if args[:2] == ["run", "python"]:
    raise SystemExit(subprocess.call([sys.executable, *args[2:]]))
if args and args[0] == "run":
    print("1 passed in 0.01s")
    raise SystemExit(0)
if args and args[0] == "build":
    output = pathlib.Path("dist")
    if "--out-dir" in args:
        output = pathlib.Path(args[args.index("--out-dir") + 1])
    output.mkdir(parents=True, exist_ok=True)
    version = pathlib.Path("VERSION").read_text().strip()
    prefix = f"micro_eval-{{version}}/"
    source_entries = {{
        ".gitignore": pathlib.Path(".gitignore").read_bytes(),
        "LICENSE": pathlib.Path("LICENSE").read_bytes(),
        "NOTICE": b"notice\\n",
        "PKG-INFO": b"Metadata-Version: 2.4\\n",
        "README.md": b"readme\\n",
        "README.zh-CN.md": b"readme zh\\n",
        "VERSION": (version + "\\n").encode(),
        "pyproject.toml": pathlib.Path("pyproject.toml").read_bytes(),
        "src/micro_eval/__init__.py": pathlib.Path("src/micro_eval/__init__.py").read_bytes(),
    }}
    with tarfile.open(output / f"micro_eval-{{version}}.tar.gz", "w:gz") as archive:
        for name, content in source_entries.items():
            info = tarfile.TarInfo(prefix + name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    with zipfile.ZipFile(output / f"micro_eval-{{version}}-py3-none-any.whl", "w") as archive:
        archive.writestr("micro_eval/__init__.py", source_entries["src/micro_eval/__init__.py"])
        archive.writestr(f"micro_eval-{{version}}.dist-info/METADATA", "Metadata-Version: 2.4\\n")
        archive.writestr(f"micro_eval-{{version}}.dist-info/WHEEL", "Wheel-Version: 1.0\\n")
        archive.writestr(
            f"micro_eval-{{version}}.dist-info/licenses/LICENSE",
            source_entries["LICENSE"],
        )
        archive.writestr(f"micro_eval-{{version}}.dist-info/RECORD", "")
    print("Successfully built release artifacts")
    raise SystemExit(0)
print("unsupported fake uv invocation", args, file=sys.stderr)
raise SystemExit(2)
'''


@pytest.fixture
def release_repo(tmp_path: Path) -> ReleaseRepo:
    origin = tmp_path / "origin.git"
    worktree = tmp_path / "release-repo"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    _run(
        ["git", "init", "--bare", "--initial-branch=main", str(origin)],
        cwd=tmp_path,
    )
    _run(
        ["git", "init", "--initial-branch=main", str(worktree)], cwd=tmp_path
    )
    _git(worktree, "config", "user.name", "Release Test")
    _git(worktree, "config", "user.email", "release-test@example.invalid")

    _write_project_file(worktree, "VERSION", f"{VERSION}\n")
    _write_project_file(worktree, "LICENSE", "license\n")
    _write_project_file(worktree, "NOTICE", "notice\n")
    _write_project_file(worktree, "README.md", "base\n")
    _write_project_file(worktree, "README.zh-CN.md", "base zh\n")
    _write_project_file(
        worktree,
        "pyproject.toml",
        "[project]\nname='release-test'\nversion='1.2.3'\n",
    )
    _write_project_file(
        worktree,
        "src/micro_eval/__init__.py",
        f'__version__ = "{VERSION}"\n',
    )
    _write_project_file(
        worktree,
        "ui/package.json",
        f'{{"name": "release-test", "version": "{VERSION}"}}\n',
    )
    _copy_project_file(worktree, "scripts/release-to-main.sh")
    _write_executable(
        worktree / "scripts/release/preflight-release.sh",
        "#!/bin/sh\necho 'full preflight passed'\n",
    )
    for relative_path in PROJECTION_FILES:
        _copy_project_file(worktree, relative_path)
    shutil.copy2(
        worktree / "scripts/release/main.gitignore", worktree / ".gitignore"
    )
    _write_project_file(
        worktree,
        "AGENTS.md",
        (PROJECT_ROOT / PUBLIC_AGENTS).read_text(encoding="utf-8"),
    )
    _write_project_file(
        worktree,
        "node_modules/.vite/vitest/cache/results.json",
        '{"local": true}\n',
    )
    _write_project_file(
        worktree,
        ".scratch/historical-ticket.md",
        "private historical work item\n",
    )
    _write_project_file(worktree, "TODOS.md", "private historical work register\n")
    _git(worktree, "add", "-f", ".")
    _git(worktree, "commit", "-m", "base main with historical leak")
    _git(worktree, "remote", "add", "origin", str(origin))
    _git(worktree, "push", "-u", "origin", "main")

    _git(worktree, "checkout", "-b", "dev")
    policy_path = worktree / "scripts/release/public-projection.toml"
    policy_path.write_text(
        policy_path.read_text(encoding="utf-8").replace(
            "127246e1c768fa0215e7f1604682801d05bdab4d",
            _git(worktree, "rev-parse", "main").stdout.strip(),
        ),
        encoding="utf-8",
    )
    _write_project_file(
        worktree,
        AGENTS_TEMPLATE,
        (PROJECT_ROOT / PUBLIC_AGENTS).read_text(encoding="utf-8"),
    )
    _write_project_file(worktree, ".codex/private.md", "dev only\n")
    _write_project_file(
        worktree,
        ".scratch/current-ticket.md",
        "private current work item\n",
    )
    _write_project_file(worktree, "TODOS.md", "private current work register\n")
    _write_project_file(worktree, "CONTEXT.md", "internal domain notes\n")
    _write_project_file(
        worktree, "src/micro_eval/release_change.txt", "projected\n"
    )
    _git(worktree, "add", "-f", ".")
    _git(worktree, "commit", "-m", "prepare release")

    _write_executable(fake_bin / "uv", _fake_uv_script())
    _write_executable(fake_bin / "npx", "#!/bin/sh\necho 'Tests 1 passed'\n")
    _write_executable(
        fake_bin / "npm",
        "#!/bin/sh\n"
        "if [ -L node_modules ]; then\n"
        "  echo 'candidate dependencies must not be symlinked' >&2\n"
        "  exit 1\n"
        "fi\n"
        "if [ \"${FAIL_CANDIDATE_BUILD:-}\" = 1 ] && [ -f ../.git ]; then\n"
        "  echo 'candidate build failed' >&2\n"
        "  exit 1\n"
        "fi\n"
        "echo 'Compiled successfully'\n",
    )
    _write_executable(fake_bin / "node", f"#!/bin/sh\necho '{VERSION}'\n")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    return ReleaseRepo(worktree=worktree, origin=origin, env=env)


def _run_release(
    repo: ReleaseRepo, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return _run(
        ["bash", "scripts/release-to-main.sh", *args],
        cwd=repo.worktree,
        env=repo.env,
        check=check,
    )


def _ref(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", ref).stdout.strip()


def _origin_ref(repo: ReleaseRepo, ref: str) -> str:
    return _bare_git(repo.origin, "rev-parse", ref).stdout.strip()


def _receipt(repo: ReleaseRepo, sha: str) -> dict[str, object]:
    path = repo.worktree / ".git/micro-eval-release/receipts" / f"{sha}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_projection(repo: ReleaseRepo) -> str:
    main_sha = _ref(repo.worktree, "main")
    receipt = _receipt(repo, main_sha)
    assert receipt["receipt_version"] == 2
    assert receipt["projection_mode"] == "single-parent"
    assert _git(repo.worktree, "show", "-s", "--format=%P", main_sha).stdout.split() == [
        receipt["previous_target_sha"]
    ]
    assert _git(repo.worktree, "merge-base", "--is-ancestor", "dev", "main", check=False).returncode == 1
    assert _git(repo.worktree, "branch", "--show-current").stdout.strip() == "dev"
    assert (
        _git(
            repo.worktree, "show", "main:src/micro_eval/release_change.txt"
        ).stdout
        == "projected\n"
    )
    for private_path in (
        ".codex/private.md",
        ".scratch/current-ticket.md",
        ".scratch/historical-ticket.md",
        "TODOS.md",
        "CONTEXT.md",
        "node_modules/.vite/vitest/cache/results.json",
    ):
        assert (
            _git(
                repo.worktree,
                "cat-file",
                "-e",
                f"main:{private_path}",
                check=False,
            ).returncode
            != 0
        )
    assert (
        _git(
            repo.worktree,
            "ls-tree",
            "-r",
            "--name-only",
            "main",
            "--",
            ".scratch",
        ).stdout
        == ""
    )
    assert _git(repo.worktree, "show", "main:AGENTS.md").stdout == (
        repo.worktree / AGENTS_TEMPLATE
    ).read_text(encoding="utf-8")
    assert _git(repo.worktree, "show", "main:.gitignore").stdout == (
        repo.worktree / "scripts/release/main.gitignore"
    ).read_text(encoding="utf-8")
    assert _receipt(repo, main_sha)["status"] == "verified"
    return main_sha


def test_help_describes_separate_verified_push(tmp_path: Path) -> None:
    result = _run(["bash", str(RELEASE_SCRIPT), "--help"], cwd=tmp_path)

    assert "--local-only" in result.stdout
    assert "stage" in result.stdout
    assert "publish --expected-sha SHA" in result.stdout
    assert "--push --expected-sha SHA" in result.stdout
    assert "--tag vX.Y.Z" in result.stdout
    assert "separate action" in result.stdout
    assert "never contacts a remote" in result.stdout


def test_conflicting_modes_are_rejected_before_release(tmp_path: Path) -> None:
    result = _run(
        ["bash", str(RELEASE_SCRIPT), "--push", "--no-push"],
        cwd=tmp_path,
        check=False,
    )

    assert result.returncode != 0
    assert "Cannot combine --push with --local-only/--no-push" in result.stderr


def test_preflight_rejects_invalid_version_before_running_tools(
    tmp_path: Path,
) -> None:
    result = _run(
        ["bash", str(PREFLIGHT_SCRIPT), "not-a-version"],
        cwd=tmp_path,
        check=False,
    )

    assert result.returncode != 0
    assert "Invalid release version" in result.stderr


def test_preflight_requires_release_evidence_and_dependency_inventory(
    tmp_path: Path,
) -> None:
    result = _run(
        ["bash", str(PREFLIGHT_SCRIPT), "1.2.3"],
        cwd=tmp_path,
        check=False,
    )

    assert result.returncode != 0
    assert "Expected one Markdown dependency inventory" in result.stderr


def test_default_release_builds_verified_public_tree_without_pushing(
    release_repo: ReleaseRepo,
) -> None:
    origin_before = _origin_ref(release_repo, "refs/heads/main")

    result = _run_release(release_repo, "dev", "main")

    main_sha = _assert_projection(release_repo)
    assert main_sha != origin_before
    assert _origin_ref(release_repo, "refs/heads/main") == origin_before
    assert "No remote push performed" in result.stdout
    assert f"publish --expected-sha {main_sha}" in result.stdout


def test_failed_candidate_gate_keeps_main_unchanged_and_stage_can_retry(
    release_repo: ReleaseRepo,
) -> None:
    main_before = _ref(release_repo.worktree, "main")
    origin_before = _origin_ref(release_repo, "refs/heads/main")
    release_repo.env["FAIL_CANDIDATE_BUILD"] = "1"

    failed = _run_release(release_repo, "stage", "dev", "main", check=False)

    assert failed.returncode != 0
    assert "candidate build failed" in failed.stdout
    assert "UI build failed on candidate public tree." in failed.stderr
    assert _ref(release_repo.worktree, "main") == main_before
    assert _origin_ref(release_repo, "refs/heads/main") == origin_before
    receipts = list(
        (release_repo.worktree / ".git/micro-eval-release/receipts").glob("*.json")
    )
    assert receipts
    assert any(
        json.loads(path.read_text(encoding="utf-8"))["status"] == "staged"
        for path in receipts
    )
    staged_sha = json.loads(receipts[0].read_text(encoding="utf-8"))["candidate_sha"]

    release_repo.env.pop("FAIL_CANDIDATE_BUILD")
    _run_release(release_repo, "stage", "dev", "main")
    assert _assert_projection(release_repo) == staged_sha


def test_verified_stage_is_idempotent(release_repo: ReleaseRepo) -> None:
    _run_release(release_repo, "stage", "dev", "main")
    first_sha = _assert_projection(release_repo)

    result = _run_release(release_repo, "stage", "dev", "main")

    assert _ref(release_repo.worktree, "main") == first_sha
    assert _receipt(release_repo, first_sha)["status"] == "verified"
    assert f"Verified main commit: {first_sha}" in result.stdout


@pytest.mark.parametrize("mode", ["--local-only", "--no-push"])
def test_explicit_local_modes_only_plan(
    release_repo: ReleaseRepo, mode: str
) -> None:
    main_before = _ref(release_repo.worktree, "main")
    origin_before = _origin_ref(release_repo, "refs/heads/main")

    result = _run_release(release_repo, "--dry-run", mode, "dev", "main")

    assert _ref(release_repo.worktree, "main") == main_before
    assert _origin_ref(release_repo, "refs/heads/main") == origin_before
    assert "Would build and verify local main only" in result.stdout


def test_unknown_tracked_path_fails_closed(release_repo: ReleaseRepo) -> None:
    _write_project_file(release_repo.worktree, "UNKNOWN-INTERNAL.md", "private\n")
    _git(release_repo.worktree, "add", "UNKNOWN-INTERNAL.md")
    _git(release_repo.worktree, "commit", "-m", "add unclassified file")

    result = _run_release(
        release_repo, "--dry-run", "dev", "main", check=False
    )

    assert result.returncode != 0
    assert "UNKNOWN-INTERNAL.md: unclassified" in result.stderr


@pytest.mark.parametrize("dry_run", [False, True])
def test_stage_rejects_polluted_target_before_preflight(
    release_repo: ReleaseRepo, dry_run: bool,
) -> None:
    repo = release_repo
    base = _ref(repo.worktree, "main")
    source_tree = _ref(repo.worktree, "dev^{tree}")
    polluted = _git(repo.worktree, "commit-tree", source_tree, "-p", base, "-m", "polluted public history").stdout.strip()
    clean_tip = _git(repo.worktree, "commit-tree", _ref(repo.worktree, "main^{tree}"), "-p", polluted, "-m", "clean-looking tip").stdout.strip()
    _git(repo.worktree, "update-ref", "refs/heads/main", clean_tip)
    args = ["stage", "--dry-run"] if dry_run else ["stage"]
    result = _run_release(repo, *args, check=False)
    assert result.returncode != 0
    assert "non-public path in history" in result.stderr
    assert "full preflight passed" not in result.stdout
    assert _ref(repo.worktree, "main") == clean_tip


def test_push_requires_verified_exact_sha(release_repo: ReleaseRepo) -> None:
    unverified_sha = _ref(release_repo.worktree, "main")

    result = _run_release(
        release_repo,
        "--push",
        "--expected-sha",
        unverified_sha,
        "dev",
        "main",
        check=False,
    )

    assert result.returncode != 0
    assert "verified release receipt not found" in result.stderr


def test_push_rejects_stale_sha(release_repo: ReleaseRepo) -> None:
    stale_sha = _ref(release_repo.worktree, "main")
    _run_release(release_repo, "dev", "main")

    result = _run_release(
        release_repo,
        "--push",
        "--expected-sha",
        stale_sha,
        "dev",
        "main",
        check=False,
    )

    assert result.returncode != 0
    assert f"not expected {stale_sha}" in result.stderr


def test_push_rejects_unverified_receipt(release_repo: ReleaseRepo) -> None:
    _run_release(release_repo, "dev", "main")
    main_sha = _assert_projection(release_repo)
    receipt_path = (
        release_repo.worktree
        / ".git/micro-eval-release/receipts"
        / f"{main_sha}.json"
    )
    receipt = _receipt(release_repo, main_sha)
    receipt["status"] = "staged"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = _run_release(
        release_repo,
        "--push",
        "--expected-sha",
        main_sha,
        "dev",
        "main",
        check=False,
    )

    assert result.returncode != 0
    assert "release receipt is not verified" in result.stderr


def test_separate_push_updates_only_origin_main(release_repo: ReleaseRepo) -> None:
    origin_before = _origin_ref(release_repo, "refs/heads/main")
    _run_release(release_repo, "dev", "main")
    main_sha = _assert_projection(release_repo)

    result = _run_release(
        release_repo,
        "publish",
        "--expected-sha",
        main_sha,
        "dev",
        "main",
    )

    assert main_sha != origin_before
    assert _origin_ref(release_repo, "refs/heads/main") == main_sha
    assert "Push target: origin/main" in result.stderr
    assert f"Verified commit: {main_sha}" in result.stderr
    assert _receipt(release_repo, main_sha)["status"] == "published"
    assert (
        _bare_git(
            release_repo.origin,
            "show-ref",
            "--verify",
            "refs/heads/dev",
            check=False,
        ).returncode
        != 0
    )


def test_publish_rejects_public_remote_with_dev_branch(
    release_repo: ReleaseRepo,
) -> None:
    origin_before = _origin_ref(release_repo, "refs/heads/main")
    _run_release(release_repo, "stage", "dev", "main")
    main_sha = _assert_projection(release_repo)
    _git(release_repo.worktree, "push", "origin", "dev:refs/heads/dev")

    result = _run_release(
        release_repo,
        "publish",
        "--expected-sha",
        main_sha,
        "dev",
        "main",
        check=False,
    )

    assert result.returncode != 0
    assert "contains forbidden branch refs/heads/dev" in result.stderr
    assert _origin_ref(release_repo, "refs/heads/main") == origin_before
    assert _receipt(release_repo, main_sha)["status"] == "verified"


def test_publish_atomically_pushes_annotated_tag_for_verified_main(
    release_repo: ReleaseRepo,
) -> None:
    _run_release(release_repo, "stage", "dev", "main")
    main_sha = _assert_projection(release_repo)
    tag = f"v{VERSION}"

    result = _run_release(
        release_repo,
        "publish",
        "--expected-sha",
        main_sha,
        "--tag",
        tag,
        "dev",
        "main",
    )

    assert _origin_ref(release_repo, "refs/heads/main") == main_sha
    assert _origin_ref(release_repo, f"refs/tags/{tag}^{{commit}}") == main_sha
    tag_type = _bare_git(
        release_repo.origin, "cat-file", "-t", f"refs/tags/{tag}"
    ).stdout.strip()
    assert tag_type == "tag"
    assert f"Annotated tag: {tag} -> {main_sha}" in result.stderr
    receipt = _receipt(release_repo, main_sha)
    assert receipt["status"] == "published"
    assert receipt["published_tag"] == tag


def test_publish_rejects_wrong_or_lightweight_release_tag(
    release_repo: ReleaseRepo,
) -> None:
    _run_release(release_repo, "stage", "dev", "main")
    main_sha = _assert_projection(release_repo)

    wrong = _run_release(
        release_repo,
        "publish",
        "--expected-sha",
        main_sha,
        "--tag",
        "v9.9.9",
        "dev",
        "main",
        check=False,
    )
    assert wrong.returncode != 0
    assert f"release tag must be exactly v{VERSION}" in wrong.stderr

    tag = f"v{VERSION}"
    _git(release_repo.worktree, "tag", tag, main_sha)
    lightweight = _run_release(
        release_repo,
        "publish",
        "--expected-sha",
        main_sha,
        "--tag",
        tag,
        "dev",
        "main",
        check=False,
    )
    assert lightweight.returncode != 0
    assert "is not an annotated tag" in lightweight.stderr


def test_atomic_tag_failure_does_not_update_remote_main(
    release_repo: ReleaseRepo,
) -> None:
    origin_before = _origin_ref(release_repo, "refs/heads/main")
    _run_release(release_repo, "stage", "dev", "main")
    main_sha = _assert_projection(release_repo)
    tag = f"v{VERSION}"
    _bare_git(release_repo.origin, "update-ref", f"refs/tags/{tag}", origin_before)

    result = _run_release(
        release_repo,
        "publish",
        "--expected-sha",
        main_sha,
        "--tag",
        tag,
        "dev",
        "main",
        check=False,
    )

    assert result.returncode != 0
    assert _origin_ref(release_repo, "refs/heads/main") == origin_before
    assert _receipt(release_repo, main_sha)["status"] == "verified"


def _next_source(repo: ReleaseRepo, content: str = "second release\n") -> None:
    _write_project_file(repo.worktree, "src/micro_eval/next_release.txt", content)
    _git(repo.worktree, "add", "src/micro_eval/next_release.txt")
    _git(repo.worktree, "commit", "-m", "prepare next public source")


def test_successive_stages_publish_one_public_chain_without_private_objects(
    release_repo: ReleaseRepo, tmp_path: Path,
) -> None:
    repo = release_repo
    base = _origin_ref(repo, "main")
    before_objects = set(_bare_git(repo.origin, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)").stdout.split())
    _write_project_file(repo.worktree, ".codex/unique-private-sentinel.txt", f"private sentinel {tmp_path.name}\n")
    _git(repo.worktree, "add", "-f", ".codex/unique-private-sentinel.txt")
    _git(repo.worktree, "commit", "-m", "private development sentinel")
    private_commit = _ref(repo.worktree, "dev")
    private_blob = _ref(repo.worktree, "dev:.codex/unique-private-sentinel.txt")
    _run_release(repo, "stage")
    first = _assert_projection(repo)
    _next_source(repo)
    second_source = _ref(repo.worktree, "dev")
    _run_release(repo, "stage")
    second = _assert_projection(repo)
    assert _receipt(repo, second)["publication_base_sha"] == base
    assert _receipt(repo, second)["previous_target_sha"] == first
    _git(repo.worktree, "tag", "-a", "ambient-tag", base, "-m", "not authorized for publication")
    _git(repo.worktree, "config", "push.followTags", "true")
    _git(repo.worktree, "config", "remote.origin.mirror", "true")
    _git(repo.worktree, "config", "remote.origin.push", "dev:refs/heads/dev")
    _run_release(repo, "publish", "--expected-sha", second)

    assert _bare_git(repo.origin, "rev-list", f"{base}..main").stdout.split() == [second, first]
    assert _bare_git(repo.origin, "for-each-ref", "--format=%(refname)").stdout.split() == ["refs/heads/main"]
    after_objects = set(_bare_git(repo.origin, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)").stdout.split())
    assert {private_commit, second_source, private_blob}.isdisjoint(after_objects - before_objects)
    clone = tmp_path / "fresh-public-clone"
    _run(["git", "clone", "--no-local", str(repo.origin), str(clone)], cwd=tmp_path)
    for oid in (private_commit, second_source, private_blob):
        assert _bare_git(repo.origin, "cat-file", "-e", oid, check=False).returncode != 0
        assert _git(clone, "cat-file", "-e", oid, check=False).returncode != 0
    reachable = _git(clone, "rev-list", "--objects", "--all").stdout
    assert private_commit not in reachable and private_blob not in reachable
    assert "unique-private-sentinel" not in reachable


def test_published_stage_and_publish_are_idempotent(release_repo: ReleaseRepo) -> None:
    _run_release(release_repo, "stage")
    sha = _assert_projection(release_repo)
    _run_release(release_repo, "publish", "--expected-sha", sha)
    _run_release(release_repo, "stage")
    assert _ref(release_repo.worktree, "main") == sha
    assert _receipt(release_repo, sha)["status"] == "published"
    _run_release(release_repo, "publish", "--expected-sha", sha)
    assert _origin_ref(release_repo, "main") == sha
    assert _receipt(release_repo, sha)["status"] == "published"


@pytest.mark.parametrize("publish_first", [False, True])
def test_policy_upgrade_preserves_publication_base(
    release_repo: ReleaseRepo, publish_first: bool,
) -> None:
    repo = release_repo
    base = _origin_ref(repo, "main")
    _run_release(repo, "stage")
    first = _assert_projection(repo)
    old_digest = _receipt(repo, first)["policy_sha256"]
    if publish_first:
        _run_release(repo, "publish", "--expected-sha", first)
    policy_path = repo.worktree / "scripts/release/public-projection.toml"
    policy_path.write_text(
        policy_path.read_text(encoding="utf-8").replace('public = [\n', 'public = [\n  "NEW-PUBLIC.md",\n', 1),
        encoding="utf-8",
    )
    _write_project_file(repo.worktree, "NEW-PUBLIC.md", "new public path\n")
    _git(repo.worktree, "add", "scripts/release/public-projection.toml", "NEW-PUBLIC.md")
    _git(repo.worktree, "commit", "-m", "expand explicit public policy")
    _run_release(repo, "stage")
    second = _assert_projection(repo)
    receipt = _receipt(repo, second)
    assert receipt["policy_sha256"] != old_digest
    assert receipt["publication_base_sha"] == (first if publish_first else base)
    assert receipt["previous_target_sha"] == first
    _run_release(repo, "publish", "--expected-sha", second)
    assert _origin_ref(repo, "main") == second


@pytest.mark.parametrize("change", ["advance", "diverge", "rollback", "missing"])
def test_remote_change_rejects_publication(release_repo: ReleaseRepo, change: str) -> None:
    repo = release_repo
    base = _origin_ref(repo, "main")
    _run_release(repo, "stage")
    first = _assert_projection(repo)
    _run_release(repo, "publish", "--expected-sha", first)
    _next_source(repo)
    _run_release(repo, "stage")
    second = _assert_projection(repo)
    assert _receipt(repo, second)["publication_base_sha"] == first
    if change == "missing":
        _bare_git(repo.origin, "update-ref", "-d", "refs/heads/main")
    elif change == "rollback":
        _bare_git(repo.origin, "update-ref", "refs/heads/main", base)
    else:
        parent = first if change == "advance" else base
        tree = _bare_git(repo.origin, "rev-parse", f"{parent}^{{tree}}").stdout.strip()
        altered = _bare_git(repo.origin, "-c", "user.name=Other Publisher", "-c", "user.email=other@example.invalid", "commit-tree", tree, "-p", parent, "-m", "independent public commit").stdout.strip()
        _bare_git(repo.origin, "update-ref", "refs/heads/main", altered)
    result = _run_release(repo, "publish", "--expected-sha", second, check=False)
    assert result.returncode != 0
    assert "public remote main" in result.stderr
    assert _receipt(repo, second)["status"] == "verified"


def test_push_guard_rejects_rollback_after_remote_inspection(release_repo: ReleaseRepo) -> None:
    repo = release_repo
    base = _origin_ref(repo, "main")
    _run_release(repo, "stage")
    first = _assert_projection(repo)
    _run_release(repo, "publish", "--expected-sha", first)
    _next_source(repo)
    _run_release(repo, "stage")
    second = _assert_projection(repo)
    real_git = shutil.which("git")
    assert real_git is not None
    fake_bin = Path(repo.env["PATH"].split(os.pathsep)[0])
    _write_executable(fake_bin / "git", f'''#!/usr/bin/env python3
import subprocess, sys
result = subprocess.run([{real_git!r}, *sys.argv[1:]], capture_output=True)
if "ls-remote" in sys.argv[1:]:
    subprocess.run([{real_git!r}, "--git-dir=" + {str(repo.origin)!r}, "update-ref", "refs/heads/main", {base!r}], check=True)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
''')
    result = _run_release(repo, "publish", "--expected-sha", second, check=False)
    assert result.returncode != 0
    assert "release pre-push guard" in result.stderr
    assert _origin_ref(repo, "main") == base
    assert _bare_git(repo.origin, "cat-file", "-e", second, check=False).returncode != 0


def test_original_pre_push_hook_remains_enforced(release_repo: ReleaseRepo) -> None:
    repo = release_repo
    before = _origin_ref(repo, "main")
    _run_release(repo, "stage")
    sha = _assert_projection(repo)
    hooks = repo.worktree / ".git/custom-hooks"
    _write_executable(hooks / "pre-push", "#!/bin/sh\necho 'existing safety hook refused' >&2\nexit 1\n")
    _git(repo.worktree, "config", "core.hooksPath", str(hooks))
    result = _run_release(repo, "publish", "--expected-sha", sha, check=False)
    assert result.returncode != 0
    assert "existing safety hook refused" in result.stderr
    assert _origin_ref(repo, "main") == before
