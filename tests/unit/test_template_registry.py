"""Tests for template packaging exclusions and symlink protection (B9, security audit F4)."""

import os

from micro_eval.server.template import TemplateRegistry


def test_excludes_micro_eval_dir(tmp_path):
    """Runtime artifacts like .micro-eval must never be packaged into a template."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "eval.yaml").write_text("test: true")
    (source / ".micro-eval").mkdir()
    (source / ".micro-eval" / "runs").mkdir()
    (source / ".micro-eval" / "runs" / "data.json").write_text("{}")

    registry = TemplateRegistry(tmp_path)
    registry.create(source, "t1", "Test")
    tpl = tmp_path / "templates" / "t1"
    assert (tpl / "eval.yaml").exists()
    assert not (tpl / ".micro-eval").exists()


def test_excludes_nested_runtime_artifacts(tmp_path):
    """Excluded names must also be stripped from within copied subdirectories."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "eval.yaml").write_text("test: true")
    nested = source / "tasks" / "sub"
    nested.mkdir(parents=True)
    (nested / "__pycache__").mkdir()
    (nested / "__pycache__" / "cache.pyc").write_text("junk")
    (nested / "task.md").write_text("do the thing")

    registry = TemplateRegistry(tmp_path)
    registry.create(source, "t-nested", "Test")
    tpl = tmp_path / "templates" / "t-nested"
    assert (tpl / "tasks" / "sub" / "task.md").exists()
    assert not (tpl / "tasks" / "sub" / "__pycache__").exists()


def test_skips_top_level_symlink(tmp_path):
    """A symlink at the top level of the source directory must not be followed or copied."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "eval.yaml").write_text("test: true")
    target = tmp_path / "secret"
    target.write_text("sensitive data")
    os.symlink(target, source / "sneaky-link")

    registry = TemplateRegistry(tmp_path)
    registry.create(source, "t2", "Test")
    tpl = tmp_path / "templates" / "t2"
    assert (tpl / "eval.yaml").exists()
    assert not (tpl / "sneaky-link").exists()


def test_skips_nested_symlink(tmp_path):
    """A symlink nested inside a copied subdirectory must not be followed or copied."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "eval.yaml").write_text("test: true")
    tasks_dir = source / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "task.md").write_text("do the thing")
    target = tmp_path / "secret"
    target.write_text("sensitive data")
    os.symlink(target, tasks_dir / "sneaky-link")

    registry = TemplateRegistry(tmp_path)
    registry.create(source, "t3", "Test")
    tpl = tmp_path / "templates" / "t3"
    assert (tpl / "tasks" / "task.md").exists()
    assert not (tpl / "tasks" / "sneaky-link").exists()


def test_update_also_excludes_and_skips_symlinks(tmp_path):
    """The update() path must apply the same exclusion and symlink protection as create()."""
    source1 = tmp_path / "source1"
    source1.mkdir()
    (source1 / "eval.yaml").write_text("test: true")

    registry = TemplateRegistry(tmp_path)
    registry.create(source1, "t4", "Test")

    source2 = tmp_path / "source2"
    source2.mkdir()
    (source2 / "eval.yaml").write_text("updated: true")
    (source2 / ".git").mkdir()
    (source2 / ".git" / "config").write_text("junk")
    target = tmp_path / "secret2"
    target.write_text("sensitive data")
    os.symlink(target, source2 / "sneaky-link")

    registry.update("t4", source2)
    tpl = tmp_path / "templates" / "t4"
    assert (tpl / "eval.yaml").read_text() == "updated: true"
    assert not (tpl / ".git").exists()
    assert not (tpl / "sneaky-link").exists()
