"""Tests for TemplateRegistry."""

import pytest

from micro_eval.server.template import (
    TemplateError,
    TemplateRegistry,
    resolve_template_dir,
)

# Payloads that must never be accepted as a template_id (GRO-172 / H1).
TRAVERSAL_IDS = [
    "..",
    ".",
    "...",
    "/etc",
    "../../../etc/ssh",
    "../evil",
    "a/b",
    "",
    "x" * 65,
    "tpl a",
    "tpl$",
    "tpl\n",
]


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


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_resolve_template_dir_rejects_traversal(registry, bad_id):
    assert resolve_template_dir(registry.templates_dir, bad_id) is None


def test_resolve_template_dir_accepts_valid(registry):
    resolved = resolve_template_dir(registry.templates_dir, "tpl-a")
    assert resolved is not None
    assert resolved.parent == registry.templates_dir.resolve()
    assert resolved.name == "tpl-a"


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_get_rejects_traversal(registry, bad_id):
    assert registry.get(bad_id) is None


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_create_rejects_traversal(registry, source_dir, bad_id):
    with pytest.raises(TemplateError, match="invalid template id"):
        registry.create(source_dir, template_id=bad_id, name="Evil")


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_update_rejects_traversal(registry, source_dir, bad_id):
    with pytest.raises(TemplateError, match="template not found"):
        registry.update(bad_id, source_dir)


@pytest.mark.parametrize("bad_id", TRAVERSAL_IDS)
def test_delete_rejects_traversal(registry, bad_id):
    assert registry.delete(bad_id) is False


def test_create_traversal_id_writes_nothing_outside_root(registry, source_dir, data_root):
    """A traversal template_id must not create anything outside templates_dir."""
    sibling = data_root / "evil"
    with pytest.raises(TemplateError):
        registry.create(source_dir, template_id="../evil", name="Evil")
    assert not sibling.exists()
