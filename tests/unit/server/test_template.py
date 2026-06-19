"""Tests for TemplateRegistry."""

import pytest

from micro_eval.server.template import TemplateError, TemplateRegistry


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / ".micro-eval-server"
    root.mkdir()
    return root


@pytest.fixture
def registry(data_root):
    return TemplateRegistry(data_root)


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "eval.yaml").write_text("project_name: test\n")
    tasks = src / "tasks"
    tasks.mkdir()
    (tasks / "task-a.yaml").write_text("id: task-a\n")
    return src


def test_create(registry, source_dir):
    meta = registry.create(source_dir, template_id="tpl-1", name="Test Template")
    assert meta.template_id == "tpl-1"
    assert meta.version == "1.0.0"
    assert registry.get("tpl-1") is not None


def test_create_duplicate_rejected(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="T")
    with pytest.raises(TemplateError, match="already exists"):
        registry.create(source_dir, template_id="tpl-1", name="T2")


def test_update_increments_version(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="T")
    (source_dir / "eval.yaml").write_text("project_name: updated\n")
    meta = registry.update("tpl-1", source_dir)
    assert meta.version == "1.0.1"


def test_list(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="A")
    registry.create(source_dir, template_id="tpl-2", name="B")
    templates = registry.list_templates()
    assert len(templates) == 2


def test_delete(registry, source_dir):
    registry.create(source_dir, template_id="tpl-1", name="T")
    assert registry.delete("tpl-1")
    assert registry.get("tpl-1") is None
