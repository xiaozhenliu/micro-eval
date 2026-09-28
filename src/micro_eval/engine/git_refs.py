"""Strict git ref resolution to exactly one locally available commit.

Shared by the plan snapshot builder, the Team Server source preflight and
the git-worktree provider so a user-supplied ``workspace.ref`` can never be
interpreted as a git option, and tree/blob/tag objects can never be mistaken
for a commit (GRO-972).
"""

from __future__ import annotations

import os
import re
import subprocess
import unicodedata
from pathlib import Path


class GitRefResolutionError(Exception):
    """Raised when a ref does not resolve to exactly one local commit.

    ``reason`` is a stable machine-readable cause: ``invalid_git_ref`` for a
    refused input, ``git_unavailable`` when git itself could not run and
    ``not_a_repository`` when the directory is not inside a git repository
    (routed back to the existing source-validation paths, not a ref verdict).
    The message is fixed and safe to display: it never contains the raw ref,
    a filesystem path, or git stdout/stderr.
    """

    REASON_INVALID_REF = "invalid_git_ref"
    REASON_GIT_UNAVAILABLE = "git_unavailable"
    REASON_NOT_A_REPOSITORY = "not_a_repository"

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


INVALID_GIT_REF_HINT = (
    "Use a branch, tag, or commit SHA that exists in the server repository "
    "and resolves to a commit. Correct the ref or fetch the required commit, "
    "then preview again."
)

_INVALID_REF_MESSAGE = "git ref cannot be resolved to a commit"
_GIT_UNAVAILABLE_MESSAGE = "git executable unavailable or failed to run"
_NOT_A_REPOSITORY_MESSAGE = "workspace source is not a git repository"

# Classified from the stderr prefix only to route the failure; the message
# itself is never surfaced. Stable across git 2.x.
_NOT_A_REPOSITORY_PREFIX = "fatal: not a git repository"

# SHA-1 commit object ids are 40 hex digits; SHA-256 object ids are 64.
_COMMIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _has_disallowed_control(ref: str) -> bool:
    """NUL, C0/C1 control categories — none can be a meaningful ref."""
    for char in ref:
        if unicodedata.category(char) == "Cc":
            return True
    return False


def _checked_ref(ref: str | None) -> str:
    """Return the rev-parse target for ``ref`` or raise a controlled error."""
    if ref is None or ref == "":
        # Existing default policy: an unset ref resolves HEAD, which must
        # itself resolve to a commit (an unborn HEAD is refused by git).
        return "HEAD"
    if not isinstance(ref, str):
        raise GitRefResolutionError(
            GitRefResolutionError.REASON_INVALID_REF, _INVALID_REF_MESSAGE
        )
    # Reject NUL and control characters (ASCII C0 plus Unicode Cc, which
    # covers the C1 block like U+0085) before spawning a subprocess: they can
    # never be a meaningful ref and must not reach an error path that echoes
    # them.
    if _has_disallowed_control(ref):
        raise GitRefResolutionError(
            GitRefResolutionError.REASON_INVALID_REF, _INVALID_REF_MESSAGE
        )
    # Leading or trailing whitespace of any kind (ASCII or Unicode, e.g.
    # U+00A0) marks a malformed input: it is neither silently trimmed nor
    # rewritten to HEAD. This also covers whitespace-only strings.
    if ref[0].isspace() or ref[-1].isspace():
        raise GitRefResolutionError(
            GitRefResolutionError.REASON_INVALID_REF, _INVALID_REF_MESSAGE
        )
    return ref


def resolve_commit(
    ref: str | None,
    *,
    repo: Path | None = None,
    repo_fd: int | None = None,
) -> str:
    """Resolve ``ref`` to one commit object id available in the local repo.

    Exactly one of ``repo`` (used as the subprocess working directory) and
    ``repo_fd`` (an open directory descriptor; the git child process fchdirs
    to it before exec, so a renamed or symlinked path cannot redirect the
    lookup) must be provided. The caller keeps ownership of ``repo_fd``: it
    is never closed here and the parent process cwd is never changed.

    ``--end-of-options`` keeps the input from being read as a git option,
    ``^{commit}`` refuses tree/blob objects and peels tags to their commit,
    ``GIT_NO_LAZY_FETCH`` stops a partial clone from fetching missing objects
    and ``GIT_TERMINAL_PROMPT`` forbids interactive credential prompts.
    """
    if (repo is None) == (repo_fd is None):
        raise ValueError("provide exactly one of repo or repo_fd")
    target = _checked_ref(ref)
    # A missing path would surface as a spawn-time FileNotFoundError that is
    # indistinguishable from a missing git executable; classify it first so
    # it keeps the source-not-available semantics of the caller.
    if repo is not None and not repo.is_dir():
        raise GitRefResolutionError(
            GitRefResolutionError.REASON_NOT_A_REPOSITORY, _NOT_A_REPOSITORY_MESSAGE
        )
    argv = [
        "git",
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{target}^{{commit}}",
    ]
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    try:
        if repo_fd is not None:
            result = subprocess.run(
                argv,
                preexec_fn=lambda: os.fchdir(repo_fd),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(
                argv,
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        # Includes FileNotFoundError when no git executable is on PATH; this
        # is a tool failure, not a "ref does not exist" verdict.
        raise GitRefResolutionError(
            GitRefResolutionError.REASON_GIT_UNAVAILABLE, _GIT_UNAVAILABLE_MESSAGE
        ) from exc
    oid = result.stdout.strip()
    if result.returncode != 0 or not _COMMIT_OID_RE.fullmatch(oid):
        if result.returncode != 0 and result.stderr.startswith(_NOT_A_REPOSITORY_PREFIX):
            raise GitRefResolutionError(
                GitRefResolutionError.REASON_NOT_A_REPOSITORY, _NOT_A_REPOSITORY_MESSAGE
            )
        raise GitRefResolutionError(
            GitRefResolutionError.REASON_INVALID_REF, _INVALID_REF_MESSAGE
        )
    return oid
