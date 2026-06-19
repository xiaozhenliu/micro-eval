"""Read-only template registry for server mode."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from micro_eval.server.models import TemplateMeta


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
        tpl_dir = self.templates_dir / template_id
        if tpl_dir.exists():
            raise TemplateError(f"template already exists: {template_id}")
        tpl_dir.mkdir(parents=True, exist_ok=False)

        for item in source_dir.iterdir():
            dest = tpl_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

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
        meta_path = self.templates_dir / template_id / "template.json"
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
        meta = self.get(template_id)
        if meta is None:
            raise TemplateError(f"template not found: {template_id}")
        tpl_dir = self.templates_dir / template_id
        for item in tpl_dir.iterdir():
            if item.name == "template.json":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in source_dir.iterdir():
            dest = tpl_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        parts = meta.version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        meta.version = ".".join(parts)
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        (tpl_dir / "template.json").write_text(meta.model_dump_json(indent=2))
        return meta

    def delete(self, template_id: str) -> bool:
        tpl_dir = self.templates_dir / template_id
        if not tpl_dir.exists():
            return False
        shutil.rmtree(tpl_dir)
        return True
