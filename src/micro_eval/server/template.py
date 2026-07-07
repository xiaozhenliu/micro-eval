"""Read-only template registry for server mode."""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import TemplateMeta

logger = logging.getLogger(__name__)

# template_id charset: alphanumerics plus dot/hyphen/underscore, 1-64 chars, and
# never a pure-dot name. Excludes '/' and rejects '.'/'..' so a caller-supplied
# id cannot escape the templates root via path traversal (H1). `\Z` (not `$`)
# anchors the end so a trailing newline cannot slip through.
_TEMPLATE_ID_RE = re.compile(r"(?!\.+\Z)[A-Za-z0-9._-]{1,64}\Z")


def resolve_template_dir(templates_dir: Path, template_id: str) -> Path | None:
    """Validate ``template_id`` and resolve it strictly inside ``templates_dir``.

    Returns the resolved template directory (which may or may not exist yet), or
    ``None`` when the id is malformed or would resolve outside the templates
    root. Mirrors ``WorkspaceManager.resolve_path``: the charset check rejects
    traversal payloads (``/etc``, ``..``, ``../../x``) and the resolve + prefix
    check is defence-in-depth. Callers decide whether non-existence is an error.
    """
    if not _TEMPLATE_ID_RE.match(template_id):
        return None
    templates_dir = Path(templates_dir)
    templates_root = templates_dir.resolve()
    tpl_dir = (templates_dir / template_id).resolve()
    if not str(tpl_dir).startswith(str(templates_root) + os.sep):
        return None
    return tpl_dir


# Runtime artifacts and OS cruft that must never be packaged into a template.
TEMPLATE_EXCLUDE_NAMES = frozenset(
    {
        ".micro-eval",
        ".git",
        "__pycache__",
        ".next",
        "node_modules",
        "report.html",
        ".DS_Store",
    }
)

TEMPLATE_EXCLUDES = shutil.ignore_patterns(*TEMPLATE_EXCLUDE_NAMES)


def _template_ignore(directory: str, contents: list[str]) -> set[str]:
    """`shutil.copytree` ignore callback: excludes runtime artifacts and symlinks.

    Symlinks are excluded (rather than followed) per security guidance (F4):
    a template source directory must not let an attacker smuggle in a link
    that copies files from outside the source tree.
    """
    ignored = set(TEMPLATE_EXCLUDES(directory, contents))
    dir_path = Path(directory)
    for name in contents:
        if name in ignored:
            continue
        item = dir_path / name
        if item.is_symlink():
            ignored.add(name)
            logger.warning("Skipping symlink in template source: %s", item)
        elif item.is_file() and item.stat().st_nlink > 1:
            ignored.add(name)
            logger.warning("Skipping hardlink in template source: %s", item)
    return ignored


def _copy_template_source(source_dir: Path, tpl_dir: Path) -> None:
    """Copy template source contents into tpl_dir, excluding runtime artifacts and symlinks."""
    for item in source_dir.iterdir():
        if item.name in TEMPLATE_EXCLUDE_NAMES:
            continue
        if item.is_symlink():
            logger.warning("Skipping symlink in template source: %s", item)
            continue
        dest = tpl_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=_template_ignore, symlinks=False)
        else:
            if item.stat().st_nlink > 1:
                logger.warning("Skipping hardlink in template source: %s", item)
                continue
            shutil.copy2(item, dest)


class TemplateError(Exception):
    pass


class TemplateRegistry:
    def __init__(self, data_root: Path):
        self.templates_dir = Path(data_root) / "templates"

    def create(
        self,
        source_dir: Path,
        template_id: str,
        name: str,
        description: str = "",
        author: str = "admin",
    ) -> TemplateMeta:
        if not source_dir.is_dir():
            raise TemplateError(f"source directory not found: {source_dir}")
        tpl_dir = resolve_template_dir(self.templates_dir, template_id)
        if tpl_dir is None:
            raise TemplateError(f"invalid template id: {template_id}")
        if tpl_dir.exists():
            raise TemplateError(f"template already exists: {template_id}")
        tpl_dir.mkdir(parents=True, exist_ok=False)

        _copy_template_source(source_dir, tpl_dir)

        now = datetime.now(timezone.utc).isoformat()
        includes = {}
        eval_yaml = tpl_dir / "eval.yaml"
        if eval_yaml.exists():
            includes["eval_yaml"] = True
        tasks_dir = tpl_dir / "tasks"
        if tasks_dir.exists():
            includes["tasks"] = [f.name for f in tasks_dir.iterdir() if f.is_file()]

        meta = TemplateMeta(
            template_id=template_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            author=author,
            includes=includes,
        )
        (tpl_dir / "template.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def get(self, template_id: str) -> TemplateMeta | None:
        tpl_dir = resolve_template_dir(self.templates_dir, template_id)
        if tpl_dir is None:
            return None
        meta_path = tpl_dir / "template.json"
        if not meta_path.exists():
            return None
        return TemplateMeta.model_validate_json(meta_path.read_text())

    def list_templates(self) -> list[TemplateMeta]:
        if not self.templates_dir.exists():
            return []
        result = []
        for entry in sorted(self.templates_dir.iterdir()):
            if not entry.is_dir():
                continue
            meta_path = entry / "template.json"
            if not meta_path.exists():
                continue
            try:
                result.append(TemplateMeta.model_validate_json(meta_path.read_text()))
            except Exception:
                continue
        return result

    def update(self, template_id: str, source_dir: Path) -> TemplateMeta:
        tpl_dir = resolve_template_dir(self.templates_dir, template_id)
        if tpl_dir is None:
            raise TemplateError(f"template not found: {template_id}")
        meta = self.get(template_id)
        if meta is None:
            raise TemplateError(f"template not found: {template_id}")
        for item in tpl_dir.iterdir():
            if item.name == "template.json":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        _copy_template_source(source_dir, tpl_dir)

        parts = meta.version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        meta.version = ".".join(parts)
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        (tpl_dir / "template.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def delete(self, template_id: str) -> bool:
        tpl_dir = resolve_template_dir(self.templates_dir, template_id)
        if tpl_dir is None or not tpl_dir.exists():
            return False
        shutil.rmtree(tpl_dir)
        return True
