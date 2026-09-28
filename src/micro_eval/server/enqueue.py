"""Atomic run admission for the Team Server.

Building the plan, checking it against what the member previewed, and
inserting the job into the queue happen under the workspace lock (shared
with archive/delete) and the project config lock (shared with the form
editor). Nothing can change the workspace state or its configuration
between the digest comparison and the insert (round-7 review, 2026-09-13).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hashlib
import os
import re
import stat

from micro_eval.config.editor import (
    ConfigEditError,
    declared_secrets,
    find_declared_secrets,
    project_lock,
    redact_text,
)
from micro_eval.config.loader import ConfigError
from micro_eval.config.planner import build_workspace_plan
from micro_eval.engine.git_refs import (
    INVALID_GIT_REF_HINT,
    GitRefResolutionError,
    resolve_commit,
)
from micro_eval.models.ids import canonical_digest
from micro_eval.models.run import RunPlan
from micro_eval.server.models import ServerConfig
from micro_eval.server.queue import QueueDB, QueueFullError
from micro_eval.server.workspace import WorkspaceError, WorkspaceManager

# The UI and worker only look here for run output on the Team Server.
SERVER_OUTPUT_DIR = ".micro-eval/runs"

# Exit codes used by ``micro-eval workspace enqueue``; the HTTP route maps
# the JSON ``error`` kind, the codes exist for shell callers.
EXIT_CODES: dict[str, int] = {
    "workspace_not_found": 1,
    "queue_full": 2,
    "workspace_not_active": 3,
    "plan_build_failed": 4,
    "plan_changed": 5,
    "workspace_unavailable": 6,
}


class EnqueueRefused(Exception):
    """Raised when a run cannot be admitted; ``payload`` is JSON-serialisable."""

    def __init__(self, kind: str, **fields: Any) -> None:
        self.kind = kind
        self.payload: dict[str, Any] = {"error": kind, **fields}
        super().__init__(kind)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES.get(self.kind, 1)


def plan_admission_digest(plan: RunPlan, ws_dir: Path | None = None) -> str:
    """Digest of everything in the plan that is not per-build noise.

    Covers task contents (via cells), configurations, guardrails, output
    directory, trace/judge settings and the evaluation contract, so the plan
    the member confirmed is exactly the plan that gets queued. ``run_id``,
    timestamps, cell ids (which embed the run id), the observation snapshot
    and server bookkeeping are excluded. With ``ws_dir`` the workspace
    sources a task copies in (``workspace.files`` / ``path`` for the
    ``files`` type, fixtures, toolchain lockfile) are fingerprinted too, so
    editing one of those files after the preview invalidates the digest
    (round-16 review, 2026-09-13).
    """
    data = plan.model_dump(mode="json")
    for volatile in ("run_id", "created_at", "same_start_snapshot", "owner", "server_context"):
        data.pop(volatile, None)
    for cell in data.get("cells", []):
        cell.pop("cell_id", None)
    if ws_dir is None:
        return canonical_digest(data)
    return canonical_digest({"plan": data, "sources": _workspace_sources_digests(plan, ws_dir)})


_SOURCE_BYTES_CAP = 256 * 1024 * 1024
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
# O_NONBLOCK: opening a FIFO with O_RDONLY blocks until a writer appears,
# which would hang the preview/enqueue request; the fstat that follows
# rejects anything that is not a regular file or directory (round-17).
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)


class _SourceBudget:
    def __init__(self) -> None:
        self.remaining = _SOURCE_BYTES_CAP

    def spend(self, count: int) -> None:
        self.remaining -= count
        if self.remaining < 0:
            raise EnqueueRefused("plan_build_failed", detail="workspace sources are too large to fingerprint")


def _source_relative_parts(raw: str) -> list[str]:
    parts = raw.split("/")
    if raw.startswith("/") or any(part in ("", ".", "..") for part in parts) or parts[0] == ".micro-eval":
        raise EnqueueRefused(
            "plan_build_failed",
            detail="workspace source paths must be relative, inside the workspace and outside .micro-eval",
        )
    return parts


def _digest_tree(fd: int, hasher: "hashlib._Hash", budget: _SourceBudget) -> None:
    """Feed a directory's names and file contents into ``hasher`` via fds."""
    for name in sorted(os.listdir(fd)):
        hasher.update(b"\x00entry:" + name.encode("utf-8", "surrogateescape"))
        try:
            child = os.open(name, _FILE_FLAGS, dir_fd=fd)
        except OSError as exc:
            raise EnqueueRefused(
                "plan_build_failed", detail=f"workspace source must not contain symlinks: {name}"
            ) from exc
        try:
            st = os.fstat(child)
            if stat.S_ISDIR(st.st_mode):
                hasher.update(b"\x00dir")
                _digest_tree(child, hasher, budget)
            elif stat.S_ISREG(st.st_mode):
                hasher.update(b"\x00file")
                _digest_file(child, hasher, budget)
            else:
                raise EnqueueRefused("plan_build_failed", detail=f"workspace source has an unsupported entry: {name}")
        finally:
            os.close(child)


def _digest_file(fd: int, hasher: "hashlib._Hash", budget: _SourceBudget) -> None:
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return
        budget.spend(len(chunk))
        hasher.update(chunk)


def _open_source_fd(ws_dir: Path, raw: str) -> int | None:
    """Open a workspace-relative source without following any path component."""
    parts = _source_relative_parts(raw)
    try:
        fd = os.open(str(ws_dir), _DIR_FLAGS)
    except OSError as exc:
        raise EnqueueRefused("workspace_unavailable", detail="workspace directory cannot be opened") from exc
    try:
        for index, part in enumerate(parts):
            flags = _FILE_FLAGS if index == len(parts) - 1 else _DIR_FLAGS
            try:
                nxt = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise EnqueueRefused(
                    "plan_build_failed", detail="workspace source must not pass through a symlink"
                ) from exc
            os.close(fd)
            fd = nxt
        opened, fd = fd, None
        return opened
    finally:
        if fd is not None:
            os.close(fd)


def _digest_source(ws_dir: Path, raw: str, budget: _SourceBudget) -> str:
    """Content digest of one workspace-relative source (file or tree).

    A missing source still digests as ``missing`` for optional fixtures and
    lockfiles; required ``files`` sources are refused by the caller.
    """
    fd = _open_source_fd(ws_dir, raw)
    if fd is None:
        return "missing"
    try:
        hasher = hashlib.sha256()
        st = os.fstat(fd)
        if stat.S_ISDIR(st.st_mode):
            hasher.update(b"tree")
            _digest_tree(fd, hasher, budget)
        elif stat.S_ISREG(st.st_mode):
            hasher.update(b"file")
            _digest_file(fd, hasher, budget)
        else:
            raise EnqueueRefused("plan_build_failed", detail="workspace source has an unsupported type")
        return hasher.hexdigest()
    finally:
        os.close(fd)


def _preflight_git_source(ws_dir: Path, task_id: str, raw: str | None, ref: str | None) -> None:
    """Refuse a missing/non-repository git source before a run enters the queue."""
    source = raw or "."
    if not raw:
        raise EnqueueRefused("plan_build_failed", detail=f"task {task_id}: workspace source not found: {source}")
    fd = _open_source_fd(ws_dir, raw)
    if fd is None:
        raise EnqueueRefused("plan_build_failed", detail=f"task {task_id}: workspace source not found: {source}")
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise EnqueueRefused(
                "plan_build_failed", detail=f"task {task_id}: workspace source is not a git repo: {source}"
            )
        try:
            git_fd = os.open(".git", _FILE_FLAGS, dir_fd=fd)
        except OSError as exc:
            raise EnqueueRefused(
                "plan_build_failed", detail=f"task {task_id}: workspace source is not a git repo: {source}"
            ) from exc
        try:
            git_mode = os.fstat(git_fd).st_mode
            if not (stat.S_ISDIR(git_mode) or stat.S_ISREG(git_mode)):
                raise EnqueueRefused(
                    "plan_build_failed", detail=f"task {task_id}: workspace source is not a git repo: {source}"
                )
        finally:
            os.close(git_fd)
        # fchdir in the child binds Git to the validated directory inode,
        # even if the source or one of its parents is renamed before exec.
        # Strict resolution: the ref may not be read as a git option and
        # must resolve to exactly one commit (GRO-972).
        try:
            resolve_commit(ref, repo_fd=fd)
        except GitRefResolutionError as exc:
            if exc.reason == GitRefResolutionError.REASON_NOT_A_REPOSITORY:
                raise EnqueueRefused(
                    "plan_build_failed",
                    detail=f"task {task_id}: workspace source is not a git repo: {source}",
                ) from exc
            if exc.reason == GitRefResolutionError.REASON_GIT_UNAVAILABLE:
                raise EnqueueRefused(
                    "plan_build_failed",
                    detail=f"task {task_id}: git executable unavailable for workspace source: {source}",
                ) from exc
            raise EnqueueRefused(
                "plan_build_failed",
                detail=f"task {task_id}: git ref cannot be resolved for workspace source: {source}",
                reason="invalid_git_ref",
                hint=INVALID_GIT_REF_HINT,
            ) from exc
    finally:
        os.close(fd)


def _workspace_sources_digests(plan: RunPlan, ws_dir: Path) -> dict[str, dict[str, str]]:
    """``{task_id: {source_path: digest}}`` for every source a task copies in."""
    budget = _SourceBudget()
    result: dict[str, dict[str, str]] = {}
    seen: set[str] = set()
    for cell in plan.cells:
        task = cell.task
        if task.id in seen:
            continue
        seen.add(task.id)
        ws = task.workspace
        if ws.type.value == "git_repo":
            _preflight_git_source(ws_dir, task.id, ws.path, ws.ref)
        file_sources: set[str] = set(ws.files or ([ws.path] if ws.path else [])) if ws.type.value == "files" else set()
        sources: list[str] = list(file_sources)
        sources.extend(fixture.path for fixture in ws.fixtures if not fixture.digest)
        if ws.toolchain is not None and ws.toolchain.lockfile:
            sources.append(ws.toolchain.lockfile)
        if not sources:
            continue
        result[task.id] = {}
        for raw in sorted(set(sources)):
            digest = _digest_source(ws_dir, raw, budget)
            if digest == "missing" and raw in file_sources:
                raise EnqueueRefused("plan_build_failed", detail=f"task {task.id}: workspace source not found: {raw}")
            result[task.id][raw] = digest
    return result


def _max_queue_size(data_root: Path) -> int:
    config_path = data_root / "server.json"
    if not config_path.exists():
        return ServerConfig().max_queue_size
    try:
        return ServerConfig.model_validate_json(config_path.read_text()).max_queue_size
    except (OSError, ValueError):
        return ServerConfig().max_queue_size


_INPUT_VALUE_RE = re.compile(r"input_value=.*?(?=, input_type=)", re.DOTALL)
_PYDANTIC_URL_RE = re.compile(r"\s*For further information visit \S+")
_ABS_PATH_RE = re.compile(r"/[\w./-]+")


def _safe_detail(message: str, roots: tuple[Path, ...] = ()) -> str:
    """Strip echoed input from validation errors and mask declared secrets.

    Pydantic repeats the offending value (``input_value=...``) in its
    messages; a pasted secret in a task or configuration must not come back
    through the refusal payload (round-9 review, 2026-09-13).
    """
    cleaned = message
    # Known directories first: they may contain spaces or non-ASCII, which
    # the generic pattern below cannot delimit (round-11 review).
    for root in sorted({str(r) for r in roots}, key=len, reverse=True):
        cleaned = cleaned.replace(root, "<path>")
    cleaned = _INPUT_VALUE_RE.sub("input_value=<omitted>", cleaned)
    cleaned = _PYDANTIC_URL_RE.sub("", cleaned)
    cleaned = _ABS_PATH_RE.sub("<path>", cleaned)
    redacted, _ = redact_text(cleaned, declared_secrets())
    return redacted


def _build_admissible_plan(ws_dir: Path, data_root: Path) -> RunPlan:
    try:
        plan = build_workspace_plan(ws_dir, strict_paths=True)
    except ConfigError as exc:
        detail = _safe_detail(str(exc), (ws_dir, data_root))
        if getattr(exc, "reason", None) == "invalid_git_ref":
            raise EnqueueRefused(
                "plan_build_failed",
                detail=detail,
                reason="invalid_git_ref",
                hint=INVALID_GIT_REF_HINT,
            ) from exc
        raise EnqueueRefused("plan_build_failed", detail=detail) from exc
    if plan.output_dir != SERVER_OUTPUT_DIR:
        raise EnqueueRefused(
            "plan_build_failed",
            detail=f"output_dir must be {SERVER_OUTPUT_DIR} on the Team Server; fix it in the Advanced tab",
        )
    # The plan is persisted verbatim in queue.db for the worker. A declared
    # secret value must never be inside it (commands, env, task text): the
    # runtime injects secrets from MICRO_EVAL_SECRET_* via required_secrets
    # (round-13 review, 2026-09-13).
    leaked = find_declared_secrets(plan.model_dump(mode="json"))
    if leaked:
        names = ", ".join(sorted(leaked))
        raise EnqueueRefused(
            "plan_build_failed",
            detail=f"plan contains the value of declared secret(s) {names}; reference them via required_secrets instead",
        )
    return plan



def _require_active(manager: WorkspaceManager, workspace_id: str) -> None:
    meta = manager.get(workspace_id)
    if meta is None:
        raise EnqueueRefused("workspace_not_found")
    if meta.status != "active":
        raise EnqueueRefused("workspace_not_active", status=meta.status)


def preview_workspace_run(manager: WorkspaceManager, workspace_id: str) -> dict[str, Any]:
    """Dry run: the plan as it would be admitted right now, plus its digest.

    Same loader, same admission rules and same digest function as
    :func:`enqueue_workspace_run`, so the preview cannot drift from what a
    later enqueue compares against.
    """
    ws_dir = manager.resolve_path(workspace_id)
    if ws_dir is None:
        raise EnqueueRefused("workspace_not_found")
    _require_active(manager, workspace_id)
    plan = _build_admissible_plan(ws_dir, manager.data_root)
    return {"plan_digest": plan_admission_digest(plan, ws_dir), "plan": plan.model_dump(mode="json")}


def enqueue_workspace_run(
    manager: WorkspaceManager,
    workspace_id: str,
    owner: str,
    *,
    expected_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Build the workspace plan and enqueue it, all under the workspace locks.

    ``expected_plan_digest`` is the :func:`plan_admission_digest` the member
    saw in the preview; any edit made since (tasks, configurations,
    guardrails, output_dir, ...) is refused with ``plan_changed``.
    """
    ws_dir = manager.resolve_path(workspace_id)
    if ws_dir is None:
        raise EnqueueRefused("workspace_not_found")
    try:
        with WorkspaceManager.lock(ws_dir), project_lock(ws_dir):
            _require_active(manager, workspace_id)
            plan = _build_admissible_plan(ws_dir, manager.data_root)
            digest = plan_admission_digest(plan, ws_dir)
            if expected_plan_digest is not None and digest != expected_plan_digest:
                raise EnqueueRefused("plan_changed", plan_digest=digest)
            db = QueueDB(manager.data_root / "queue.db")
            try:
                result = db.enqueue(
                    workspace_id=workspace_id,
                    owner=owner,
                    plan_json=plan.model_dump_json(),
                    max_queue_size=_max_queue_size(manager.data_root),
                )
            except QueueFullError as exc:
                raise EnqueueRefused("queue_full", current=exc.current, maximum=exc.maximum) from exc
            finally:
                db.close()
    except (WorkspaceError, ConfigEditError) as exc:
        raise EnqueueRefused(
            "workspace_unavailable", detail=_safe_detail(str(exc), (ws_dir, manager.data_root))
        ) from exc
    result["plan_digest"] = digest
    return result
