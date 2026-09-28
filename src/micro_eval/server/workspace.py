"""Workspace lifecycle management for server mode."""

from __future__ import annotations

import fcntl
import logging
import os
import re
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import WorkspaceMeta, new_workspace_id

logger = logging.getLogger(__name__)

_WS_ID_RE = re.compile(r"^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$")


class WorkspaceError(Exception):
    pass


_RUNTIME_DIR = ".micro-eval"
_LOCK_FILE = "workspace.lock"
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_workspace_lock(ws_dir: Path) -> int:
    """Open ``<ws_dir>/.micro-eval/workspace.lock`` without following symlinks.

    Each component is opened relative to its parent descriptor; the runtime
    directory is created when missing. Returns the lock fd (caller closes).
    """
    try:
        ws_fd = os.open(str(ws_dir), _DIR_FLAGS)
    except OSError as exc:
        raise WorkspaceError("workspace directory cannot be opened") from exc
    try:
        try:
            runtime_fd = os.open(_RUNTIME_DIR, _DIR_FLAGS, dir_fd=ws_fd)
        except FileNotFoundError:
            try:
                os.mkdir(_RUNTIME_DIR, 0o755, dir_fd=ws_fd)
            except FileExistsError:
                pass  # created concurrently; open it below
            runtime_fd = os.open(_RUNTIME_DIR, _DIR_FLAGS, dir_fd=ws_fd)
        except OSError as exc:
            # ELOOP / ENOTDIR: .micro-eval is a symlink or a file.
            raise WorkspaceError("workspace runtime directory must be a plain directory") from exc
    finally:
        os.close(ws_fd)
    try:
        fd = os.open(_LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=runtime_fd)
    except OSError as exc:
        raise WorkspaceError("workspace lock cannot be opened") from exc
    finally:
        os.close(runtime_fd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise WorkspaceError("workspace lock must be a plain file")
    except BaseException:
        os.close(fd)
        raise
    return fd


class WorkspaceManager:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.workspaces_dir = self.data_root / "workspaces"

    def resolve_path(self, workspace_id: str) -> Path | None:
        if not _WS_ID_RE.match(workspace_id):
            return None
        ws_root = self.workspaces_dir.resolve()
        unresolved = ws_root / workspace_id
        # A workspace directory that is itself a symlink (even to a sibling
        # workspace under the same root) would let one id act as another;
        # refuse it before resolving anything (round-6 review, 2026-09-12).
        if unresolved.is_symlink() or not unresolved.is_dir():
            return None
        try:
            real_ws = unresolved.resolve(strict=True)
            real_root = ws_root.resolve(strict=True)
        except OSError:
            return None
        if not str(real_ws).startswith(str(real_root) + "/"):
            return None
        meta_path = real_ws / "workspace.json"
        if meta_path.is_symlink() or not meta_path.is_file():
            return None
        try:
            meta = WorkspaceMeta.model_validate_json(meta_path.read_text())
        except Exception:
            return None
        if meta.workspace_id != workspace_id:
            return None
        return real_ws

    @staticmethod
    @contextmanager
    def lock(ws_dir: Path) -> Iterator[None]:
        """Serialise workspace state transitions with queue admission.

        Archiving, deleting and enqueueing take this same lock so a job can
        never be admitted into a workspace that is being archived (round-6
        review). The lock file is reached through directory descriptors with
        ``O_NOFOLLOW`` at every step: a ``.micro-eval`` symlink would
        otherwise redirect the lock outside the workspace and void the
        mutual exclusion (round-7 review, 2026-09-13).
        """
        fd = _open_workspace_lock(ws_dir)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def create(
        self,
        name: str,
        owner: str,
        template_id: str | None = None,
        description: str = "",
    ) -> WorkspaceMeta:
        ws_id = new_workspace_id()
        ws_dir = self.workspaces_dir / ws_id
        ws_dir.mkdir(parents=True, exist_ok=False)
        try:
            (ws_dir / ".micro-eval" / "runs").mkdir(parents=True, exist_ok=True)

            template_version = None
            if template_id:
                from micro_eval.server.template import (
                    TEMPLATE_EXCLUDE_NAMES,
                    _template_ignore,
                    resolve_template_dir,
                )
                tpl_dir = resolve_template_dir(self.data_root / "templates", template_id)
                if tpl_dir is None or not tpl_dir.exists():
                    raise WorkspaceError(f"template not found: {template_id}")
                tpl_meta_path = tpl_dir / "template.json"
                if tpl_meta_path.exists():
                    from micro_eval.server.models import TemplateMeta
                    tpl_meta = TemplateMeta.model_validate_json(tpl_meta_path.read_text())
                    template_version = tpl_meta.version
                for item in tpl_dir.iterdir():
                    if item.name == "template.json":
                        continue
                    if item.name in TEMPLATE_EXCLUDE_NAMES:
                        continue
                    if item.is_symlink():
                        logger.warning("Skipping symlink in template source: %s", item)
                        continue
                    dest = ws_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, ignore=_template_ignore, symlinks=False)
                    else:
                        if item.stat().st_nlink > 1:
                            logger.warning("Skipping hardlink in template source: %s", item)
                            continue
                        shutil.copy2(item, dest)
            else:
                (ws_dir / "eval.yaml").write_text("# micro-eval configuration\nproject_name: unnamed\n")

            now = datetime.now(timezone.utc).isoformat()
            meta = WorkspaceMeta(
                workspace_id=ws_id,
                name=name,
                owner=owner,
                template_id=template_id,
                template_version=template_version,
                created_at=now,
                description=description,
            )
            (ws_dir / "workspace.json").write_text(meta.model_dump_json(indent=2))
            return meta
        except WorkspaceError:
            shutil.rmtree(ws_dir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(ws_dir, ignore_errors=True)
            raise WorkspaceError(
                f"workspace creation failed: {exc}. "
                "If the template contains .micro-eval/, re-register it after upgrading."
            ) from exc

    def get(self, workspace_id: str) -> WorkspaceMeta | None:
        ws_dir = self.resolve_path(workspace_id)
        if ws_dir is None:
            return None
        meta_path = ws_dir / "workspace.json"
        if not meta_path.exists():
            return None
        return WorkspaceMeta.model_validate_json(meta_path.read_text())

    def list_workspaces(self, include_archived: bool = False) -> list[WorkspaceMeta]:
        if not self.workspaces_dir.exists():
            return []
        result = []
        for entry in sorted(self.workspaces_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "workspace.json"
            if not meta_path.exists():
                continue
            try:
                meta = WorkspaceMeta.model_validate_json(meta_path.read_text())
                if not include_archived and meta.status == "archived":
                    continue
                result.append(meta)
            except Exception:
                continue
        return result

    def update(self, workspace_id: str, **fields) -> WorkspaceMeta | None:
        ws_dir = self.resolve_path(workspace_id)
        if ws_dir is None:
            return None
        with self.lock(ws_dir):
            meta = self.get(workspace_id)
            if meta is None:
                return None
            allowed = {"name", "description", "status"}
            if fields.get("status") == "archived" and meta.status != "archived":
                # Same lock as queue admission: no job can slip in between
                # this check and the state change.
                self._refuse_pending_jobs(workspace_id, "archiving")
            for key, value in fields.items():
                if key in allowed:
                    setattr(meta, key, value)
            (ws_dir / "workspace.json").write_text(meta.model_dump_json(indent=2))
            return meta

    def delete(self, workspace_id: str) -> bool:
        ws_dir = self.resolve_path(workspace_id)
        if ws_dir is None:
            return False
        with self.lock(ws_dir):
            # Same lock as queue admission (round-6 review): a job cannot be
            # admitted into a workspace that is being removed.
            self._refuse_pending_jobs(workspace_id, "deleting")
            shutil.rmtree(ws_dir)
        return True

    def _refuse_pending_jobs(self, workspace_id: str, action: str) -> None:
        """Raise when queued or running jobs still reference the workspace.

        Callers hold :meth:`lock`, so queue admission cannot interleave with
        the state change that follows this check.
        """
        from micro_eval.server.queue import QueueDB

        db_path = self.data_root / "queue.db"
        if not db_path.exists():
            return
        db = QueueDB(db_path)
        try:
            if db.has_pending_jobs(workspace_id):
                raise WorkspaceError(f"workspace has pending jobs; cancel them before {action}")
        finally:
            db.close()
