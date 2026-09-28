"""Workspace lifecycle management for server mode."""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import WorkspaceMeta, new_workspace_id

logger = logging.getLogger(__name__)

_WS_ID_RE = re.compile(r"^ws-\d{8}T\d{6}Z-[a-f0-9]{8}$")


class WorkspaceError(Exception):
    pass


class WorkspaceManager:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.workspaces_dir = self.data_root / "workspaces"

    def resolve_path(self, workspace_id: str) -> Path | None:
        if not _WS_ID_RE.match(workspace_id):
            return None
        ws_dir = (self.workspaces_dir / workspace_id).resolve()
        ws_root = self.workspaces_dir.resolve()
        if not str(ws_dir).startswith(str(ws_root) + "/"):
            return None
        if not ws_dir.exists():
            return None
        try:
            real_ws = ws_dir.resolve(strict=True)
            real_root = ws_root.resolve(strict=True)
            if not str(real_ws).startswith(str(real_root) + "/"):
                return None
            return real_ws
        except OSError:
            return None

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
        meta = self.get(workspace_id)
        if meta is None:
            return None
        allowed = {"name", "description", "status"}
        for key, value in fields.items():
            if key in allowed:
                setattr(meta, key, value)
        (ws_dir / "workspace.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def delete(self, workspace_id: str) -> bool:
        ws_dir = self.resolve_path(workspace_id)
        if ws_dir is None:
            return False
        shutil.rmtree(ws_dir)
        return True
