"""Tests for engine/git_refs.py — strict ref → commit resolution (GRO-972).

The matrices mirror the acceptance rules in GRO-972: every accepted form
must resolve to exactly one commit object (tags peeled), every option-like,
non-commit, ambiguous, unborn or malformed input must be refused before any
git subprocess can interpret it, and error messages must never echo the raw
ref, a path, or git output.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from micro_eval.engine import git_refs
from micro_eval.engine.git_refs import GitRefResolutionError, resolve_commit

_GIT_IDENTITY = ["-c", "user.email=t@t.example", "-c", "user.name=T"]
_INVALID = GitRefResolutionError.REASON_INVALID_REF
_UNAVAILABLE = GitRefResolutionError.REASON_GIT_UNAVAILABLE


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *_GIT_IDENTITY, *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(path: Path, *, object_format: str | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    argv = ["git", "init", "-q", "-b", "main"]
    if object_format is not None:
        argv += ["--object-format", object_format]
    subprocess.run(argv + [str(path)], check=True, capture_output=True)
    return path


def _commit(repo: Path, message: str) -> str:
    _git(repo, "commit", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _repo_with_two_commits(path: Path) -> tuple[Path, str, str]:
    repo = _make_repo(path)
    first = _commit(repo, "first")
    second = _commit(repo, "second")
    return repo, first, second


# ---------------------------------------------------------------------------
# Accepted forms
# ---------------------------------------------------------------------------


class TestAcceptedRefs:
    def test_none_defaults_to_head(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        assert resolve_commit(None, repo=repo) == second

    def test_empty_string_defaults_to_head(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        assert resolve_commit("", repo=repo) == second

    def test_branch(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        _git(repo, "branch", "feature/x", first)
        assert resolve_commit("feature/x", repo=repo) == first

    def test_full_branch_ref(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        assert resolve_commit("refs/heads/main", repo=repo) == second

    def test_remote_tracking_ref(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        _git(repo, "update-ref", "refs/remotes/origin/main", first)
        assert resolve_commit("origin/main", repo=repo) == first
        assert resolve_commit("refs/remotes/origin/main", repo=repo) == first

    def test_lightweight_tag(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        _git(repo, "tag", "light", first)
        assert resolve_commit("light", repo=repo) == first

    def test_annotated_tag_peels_to_commit(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        _git(repo, "tag", "-a", "ann", "-m", "message", first)
        tag_object = _git(repo, "rev-parse", "ann").stdout.strip()
        resolved = resolve_commit("ann", repo=repo)
        assert resolved == first
        assert resolved != tag_object

    def test_annotated_tag_chain_peels_to_commit(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        _git(repo, "tag", "-a", "inner", "-m", "inner", first)
        _git(repo, "tag", "-a", "outer", "-m", "outer", "inner")
        assert resolve_commit("outer", repo=repo) == first

    def test_full_commit_sha(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        assert resolve_commit(first, repo=repo) == first

    def test_short_commit_sha(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        assert resolve_commit(first[:8], repo=repo) == first

    def test_ancestry_expressions(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        assert resolve_commit("HEAD~1", repo=repo) == first
        assert resolve_commit("HEAD^", repo=repo) == first

    def test_reflog_expression(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        assert resolve_commit("HEAD@{0}", repo=repo) == second

    def test_sha256_repository(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path / "sha256", object_format="sha256")
        head = _commit(repo, "sha256 commit")
        assert len(head) == 64
        assert resolve_commit(head, repo=repo) == head
        assert resolve_commit(None, repo=repo) == head
        assert resolve_commit(head[:12], repo=repo) == head


# ---------------------------------------------------------------------------
# Refused forms
# ---------------------------------------------------------------------------


class TestRefusedRefs:
    @pytest.mark.parametrize(
        "ref",
        [
            "--help",
            "--show-toplevel",
            "--exec=touch{{pwned}}",
            "--output=../escape",
        ],
    )
    def test_option_like_input_is_refused(self, tmp_path: Path, ref: str) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(ref.replace("{{pwned}}", "/pwned"), repo=repo)
        assert info.value.reason == _INVALID

    def test_tree_object_is_refused(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit("HEAD^{tree}", repo=repo)
        assert info.value.reason == _INVALID

    def test_blob_object_is_refused(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        (repo / "file.txt").write_text("content\n")
        _git(repo, "add", "file.txt")
        _commit(repo, "add file")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit("HEAD:file.txt", repo=repo)
        assert info.value.reason == _INVALID

    def test_tag_pointing_at_tree_is_refused(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
        _git(repo, "tag", "tree-tag", tree)
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit("tree-tag", repo=repo)
        assert info.value.reason == _INVALID

    def test_annotated_tag_pointing_at_tree_is_refused(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
        _git(repo, "tag", "-a", "ann-tree", "-m", "m", tree)
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit("ann-tree", repo=repo)
        assert info.value.reason == _INVALID

    def test_missing_ref_is_refused(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit("nonexistent-branch-xyz", repo=repo)
        assert info.value.reason == _INVALID

    def test_directory_outside_any_repository_is_not_a_ref_verdict(
        self, tmp_path: Path
    ) -> None:
        plain = tmp_path / "not-a-repo"
        plain.mkdir()
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(None, repo=plain)
        assert info.value.reason == GitRefResolutionError.REASON_NOT_A_REPOSITORY
        assert str(info.value) == "workspace source is not a git repository"

    def test_ambiguous_short_sha_is_refused(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
        seen: dict[str, str] = {}
        for index in range(4000):
            sha = _git(repo, "commit-tree", tree, "-m", f"ambiguous {index}").stdout.strip()
            prefix = sha[:4]
            other = seen.get(prefix)
            if other is not None and other != sha:
                with pytest.raises(GitRefResolutionError) as info:
                    resolve_commit(prefix, repo=repo)
                assert info.value.reason == _INVALID
                return
            seen[prefix] = sha
        pytest.fail("could not construct two commits sharing a 4-hex prefix")

    def test_unborn_head_is_refused(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path / "empty")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(None, repo=repo)
        assert info.value.reason == _INVALID

    @pytest.mark.parametrize("ref", [" ", "  \t "])
    def test_whitespace_only_ref_is_refused(self, tmp_path: Path, ref: str) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(ref, repo=repo)
        assert info.value.reason == _INVALID

    def test_leading_space_ref_is_not_trimmed_to_head(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(" main", repo=repo)
        assert info.value.reason == _INVALID

    @pytest.mark.parametrize("ref", ["bad\x00ref", "line\nbreak", "tab\tref", "del\x7f"])
    def test_control_characters_are_refused_before_subprocess(
        self, tmp_path: Path, ref: str
    ) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(ref, repo=repo)
        assert info.value.reason == _INVALID

    @pytest.mark.parametrize(
        "ref",
        [
            "\xa0main",  # leading NBSP
            "main\xa0",  # trailing NBSP
            "main\u2028",  # line separator
            "main\u3000",  # full-width space
            "\x85main",  # C1 NEL
            "\x9fmain",  # C1 block
        ],
    )
    def test_unicode_whitespace_and_c1_are_refused_before_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ref: str
    ) -> None:
        """Round-1 review: git accepts some of these as ref names, so the
        resolver must refuse them itself, before any subprocess runs."""
        repo, first, second = _repo_with_two_commits(tmp_path / "r")

        def no_spawn(argv, **kwargs):  # noqa: ANN001, ARG001
            raise AssertionError("ref validation must happen before spawning git")

        monkeypatch.setattr(git_refs.subprocess, "run", no_spawn)
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(ref, repo=repo)
        assert info.value.reason == _INVALID

    def test_non_string_ref_is_refused(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(12345, repo=repo)  # type: ignore[arg-type]
        assert info.value.reason == _INVALID

    def test_error_message_never_echoes_the_ref(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        marker = "leaky-token-9f13a"
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(f"--exec={marker}", repo=repo)
        assert marker not in str(info.value)
        assert str(repo) not in str(info.value)
        assert str(info.value) == "git ref cannot be resolved to a commit"


# ---------------------------------------------------------------------------
# Repository descriptor contract
# ---------------------------------------------------------------------------


class TestDescriptorContract:
    def test_repo_and_repo_fd_are_mutually_exclusive(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        fd = os.open(str(repo), os.O_RDONLY | os.O_DIRECTORY)
        try:
            with pytest.raises(ValueError):
                resolve_commit(None, repo=repo, repo_fd=fd)
            with pytest.raises(ValueError):
                resolve_commit(None)
        finally:
            os.close(fd)

    def test_fd_mode_matches_path_mode(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        fd = os.open(str(repo), os.O_RDONLY | os.O_DIRECTORY)
        try:
            assert resolve_commit(None, repo_fd=fd) == resolve_commit(None, repo=repo)
            assert resolve_commit("HEAD~1", repo_fd=fd) == first
        finally:
            os.close(fd)

    def test_fd_mode_does_not_close_the_caller_fd(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        fd = os.open(str(repo), os.O_RDONLY | os.O_DIRECTORY)
        try:
            resolve_commit(None, repo_fd=fd)
            os.fstat(fd)  # still owned by the caller
        finally:
            os.close(fd)

    def test_fd_mode_never_changes_the_parent_cwd(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        before = os.getcwd()
        fd = os.open(str(repo), os.O_RDONLY | os.O_DIRECTORY)
        try:
            resolve_commit(None, repo_fd=fd)
            assert os.getcwd() == before
        finally:
            os.close(fd)
            os.chdir(before)

    def test_fd_mode_ignores_a_replaced_directory_path(self, tmp_path: Path) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        moved = tmp_path / "moved"
        fd = os.open(str(repo), os.O_RDONLY | os.O_DIRECTORY)
        try:
            repo.rename(moved)
            # The open descriptor still anchors the lookup to the original
            # inode, so HEAD keeps resolving even though the path is gone.
            assert resolve_commit(None, repo_fd=fd) == second
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# Subprocess hardening
# ---------------------------------------------------------------------------


class TestSubprocessHardening:
    def _capture_run(self, monkeypatch: pytest.MonkeyPatch) -> dict:
        captured: dict = {}
        real_run = subprocess.run

        def spying_run(argv, **kwargs):
            captured["argv"] = argv
            captured["env"] = kwargs.get("env")
            return real_run(argv, **kwargs)

        monkeypatch.setattr(git_refs.subprocess, "run", spying_run)
        return captured

    def test_argv_uses_verify_end_of_options_and_commit_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        captured = self._capture_run(monkeypatch)
        resolve_commit("main", repo=repo)
        argv = captured["argv"]
        assert argv[:5] == ["git", "rev-parse", "--verify", "--end-of-options", "main^{commit}"]
        env = captured["env"]
        assert env is not None
        assert env.get("GIT_NO_LAZY_FETCH") == "1"
        assert env.get("GIT_TERMINAL_PROMPT") == "0"
        assert env.get("PATH") == os.environ.get("PATH")

    def test_missing_git_executable_reports_tool_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, first, second = _repo_with_two_commits(tmp_path / "r")
        monkeypatch.setenv("PATH", "")
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(None, repo=repo)
        assert info.value.reason == _UNAVAILABLE
        assert str(info.value) == "git executable unavailable or failed to run"


# ---------------------------------------------------------------------------
# Partial clone: no automatic object fetch
# ---------------------------------------------------------------------------


class TestPartialCloneNoLazyFetch:
    def test_missing_commit_is_not_fetched_automatically(self, tmp_path: Path) -> None:
        origin = _make_repo(tmp_path / "origin")
        _commit(origin, "first")
        # Clone first; the commit under test is created on the origin
        # afterwards so it genuinely does not exist in either clone.
        # --no-local forces a real transport so the partial-clone promisor
        # configuration is registered on each clone.
        def make_clone(name: str) -> Path:
            clone = tmp_path / name
            subprocess.run(
                ["git", "clone", "-q", "--filter=blob:none", "--no-local", str(origin), str(clone)],
                check=True,
                capture_output=True,
            )
            return clone

        control = make_clone("control")
        guarded = make_clone("guarded")
        missing = _commit(origin, "second")

        # Control clone: without the guard, git lazily fetches the commit
        # from the promisor remote and the bare rev-parse succeeds.
        fetched = subprocess.run(
            ["git", "rev-parse", "--verify", f"{missing}^{{commit}}"],
            cwd=control,
            capture_output=True,
            text=True,
            check=False,
        )
        assert fetched.returncode == 0

        # Guarded clone: resolve_commit refuses and the object is still
        # absent locally (checked with the guard env so the probe itself
        # cannot lazily fetch).
        with pytest.raises(GitRefResolutionError) as info:
            resolve_commit(missing, repo=guarded)
        assert info.value.reason == _INVALID
        probe = subprocess.run(
            ["git", "cat-file", "-e", missing],
            cwd=guarded,
            capture_output=True,
            text=True,
            check=False,
            env=dict(os.environ, GIT_NO_LAZY_FETCH="1"),
        )
        assert probe.returncode != 0


def test_invalid_git_ref_hint_is_stable() -> None:
    assert git_refs.INVALID_GIT_REF_HINT == (
        "Use a branch, tag, or commit SHA that exists in the server repository "
        "and resolves to a commit. Correct the ref or fetch the required commit, "
        "then preview again."
    )
